"""Analysator: neuer Haupt-Tab (siehe ToDo.md), importiert eine bestehende
Geschichte/Novelle als Rohtext und erzeugt daraus automatisch ein
vollstaendiges Projekt zum Neu-Schreiben - siehe app/core/analysator.py fuer
die eigentliche Zerlege-/Zusammenfassungslogik.

Zwei Endpunkte, analog zum Automatikmodus-Muster (app/api/pipeline.py:
automatik_start/automatik_status): "starten" legt SOFORT ein neues Projekt
an (wie app/api/projects.py:projekt_anlegen) und haengt die eigentliche,
lang laufende Analyse als FastAPI-BackgroundTask an - der Rueckgabewert
(ordner) ist von Anfang an fix, das Frontend pollt danach "status", bis
"abgeschlossen" gesetzt ist. Bewusst KEIN automatisches Umbenennen des
Projektordners nach dem vom Modell vorgeschlagenen Titel (anders als beim
Architekten-Interview) - erspart die sonst noetige Nachverfolgung eines
sich waehrenddessen aendernden Ordnerpfads waehrend des Hintergrund-Laufs;
der naechste normale Speichervorgang in GeruestPage (app/api/projects.py:
geruest_schreiben) benennt bei Bedarf ohnehin automatisch um."""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import ValidationError

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.core import analysator as an
from app.core import architekt as arch
from app.core import pdf_text
from app.core import uebersetzer as uebs
from app.core import projekt_dateien as pd
from app.core.epoche_vorschlag_schema import EpocheVorschlagAntwortLLM
from app.core.import_bereinigung import fuelltexte_entfernen, sprache_erkennen
from app.core.import_merkmale import (
    erzaehlperspektive_erkennen, explizitheit_bewerten, hoechste_stufe, jugendschutz_aus_stufe, tempus_erkennen,
)
from app.core.ollama_client import OllamaFehler, sammle_antwort
from app.core.textutil import woerter
from app.schemas import (
    AnalyseEintrag,
    AnalysatorEpocheVorschlagAnfrage,
    AnalysatorPdfTextAntwort,
    AnalysatorStartAnfrage,
    AnalysatorStartAntwort,
    AnalysatorStatusAntwort,
    Benutzer,
    FuelltextVorschauAnfrage,
    FuelltextVorschauAntwort,
    UebersetzenStartAnfrage,
    UebersetzenStartAntwort,
    UebersetzenStatusAntwort,
)
from app.services import (
    epoche_vollstaendig_pruefen, neuer_projekt_pfad, ollama_basis_url, projekt_pfad, projekte_wurzel, rollen_modell_override,
)

router = APIRouter(prefix="/api", tags=["analysator"])


def _status_update(projekt_root, **felder) -> dict:
    status = an.status_lesen(projekt_root)
    status.update(felder)
    an.status_schreiben(projekt_root, status)
    return status


def _log_anhaengen(projekt_root, zeile: str, **weitere_felder) -> dict:
    status = an.status_lesen(projekt_root)
    status["log"] = list(status.get("log", [])) + [zeile]
    status.update(weitere_felder)
    an.status_schreiben(projekt_root, status)
    return status


async def _analysieren_lauf(settings: Settings, projekt_root, ssh_ziel_id: str | None, text: str) -> None:
    _status_update(
        projekt_root, laeuft=True, phase="teilen", aktuelles_kapitel=None, gesamt_kapitel=None,
        log=["Text wird in Kapitel aufgeteilt..."], abgeschlossen=False, fehler=None,
    )
    try:
        vorb = an.vorbereiten(text)
        abschnitte = vorb.abschnitte
        if not abschnitte:
            raise ValueError("Im importierten Text konnte kein auswertbarer Inhalt gefunden werden.")
        gesamt = len(abschnitte)
        sprache = vorb.sprache
        if sprache == "en":
            _log_anhaengen(projekt_root, "Sprache: Englisch erkannt - die Analyse liefert alles auf Deutsch.")
        if vorb.entfernt:
            pd.schreib(
                projekt_root / "projekt" / "analysator_entfernt.md",
                "# Beim Import entfernter Fülltext\n\n" + "\n\n---\n\n".join(vorb.entfernt),
                force=True,
            )
            _log_anhaengen(
                projekt_root,
                f"{len(vorb.entfernt)} Fülltext-Absatz/Absätze (Disclaimer, A/N, Danksagung o.ä.) entfernt "
                f"- nachzulesen in projekt/analysator_entfernt.md.",
            )
        if vorb.verworfene_abschnitte:
            _log_anhaengen(projekt_root, f"{vorb.verworfene_abschnitte} reine Anmerkungs-Kapitel verworfen.")
        quelle = {
            "stichwort": "anhand der Kapitelüberschriften (Kapitel/Chapter)",
            "markdown": "anhand von Überschriften",
            "absaetze": "nach Absätzen (keine Kapitelüberschriften gefunden)",
        }[vorb.kapitel_quelle]
        _log_anhaengen(projekt_root, f"{gesamt} Kapitel erkannt, {quelle}.", gesamt_kapitel=gesamt)

        analysator_persona = pd.lies(settings.shared_personas_dir / "analysator.txt")
        eintraege: list[tuple[an.KapitelAnalyse, int]] = []
        stufen: list[str] = []

        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            for i, abschnitt in enumerate(abschnitte, start=1):
                _log_anhaengen(
                    projekt_root, f"Analysiere Kapitel {i} von {gesamt}...",
                    phase="kapitel_analyse", aktuelles_kapitel=i,
                )
                # Sehr lange Kapitel passen nicht in EINEN Aufruf (Kontextfenster) -
                # in Teile zerlegen und die Teil-Analysen danach zusammenfuegen.
                teile = an.abschnitt_in_teile(abschnitt)
                if len(teile) > 1:
                    _log_anhaengen(
                        projekt_root, f"Kapitel {i} ist sehr lang ({woerter(abschnitt)} Wörter) - Analyse in {len(teile)} Teilen.",
                    )
                originaltitel = vorb.titel[i - 1] if i - 1 < len(vorb.titel) else ""
                teil_analysen = []
                for k, teil in enumerate(teile, start=1):
                    antwort, _meta = await sammle_antwort(
                        base_url, "analysator",
                        an.kapitel_analyse_system(analysator_persona),
                        an.kapitel_analyse_user(
                            teil, sprache, index=i, gesamt=gesamt, originaltitel=originaltitel, teil=(k, len(teile)),
                        ),
                        modell_override=rollen_modell_override(settings, "analysator"),
                    )
                    teil_analysen.append(an.kapitel_analyse_parsen(antwort))
                analyse = an.analysen_zusammenfuehren(teil_analysen)
                if "nicht ersichtlich" in analyse.titel:
                    analyse.titel = originaltitel or f"Abschnitt {i}"
                # Explizitheit: Woerterlisten-Zaehlung am ganzen Kapiteltext UND Urteil der KI
                stufen.append(hoechste_stufe([explizitheit_bewerten(abschnitt), analyse.explizitheit]))
                eintraege.append((analyse, woerter(abschnitt)))

            # Aus dem GANZEN Text gezaehlte Merkmale (nicht aus Zusammenfassungen geschaetzt)
            fakten = {
                "jugendschutz": jugendschutz_aus_stufe(hoechste_stufe(stufen)),
                "perspektive": erzaehlperspektive_erkennen(vorb.bereinigter_text),
                "tempus": tempus_erkennen(vorb.bereinigter_text),
            }
            _log_anhaengen(
                projekt_root,
                f"Aus dem Text ermittelt: Jugendschutz-Stufe {fakten['jugendschutz']}, "
                f"Perspektive {fakten['perspektive'] or 'unklar'}, Tempus {fakten['tempus'] or 'unklar'}.",
            )
            _log_anhaengen(
                projekt_root, "Fasse Gesamt-Gerüst zusammen...", phase="synthese", aktuelles_kapitel=None,
            )
            epoche_architekt_persona = pd.persona_lesen(projekt_root, "architekt")
            synth_antwort, _meta = await sammle_antwort(
                base_url, "analysator",
                an.synthese_system(analysator_persona, epoche_architekt_persona),
                an.synthese_user(
                    an.kapitel_analysen_text_bauen(eintraege), an.textauszug_bauen(vorb.bereinigter_text), sprache,
                    fakten,
                ),
                modell_override=rollen_modell_override(settings, "analysator"),
            )

        geruest_text = an.geruest_zusammenbauen(synth_antwort, an.kapitelplan_block_bauen(eintraege), fakten)
        pd.schreib(pd.geruest_datei(projekt_root / "projekt"), geruest_text, force=True)

        ausgangslage = arch.ausgangslage_erkennen(geruest_text)
        if ausgangslage:
            pd.schreib(
                pd.stand_datei(projekt_root / "projekt", 0),
                "# STAND VOR KAPITEL EINS\n\n" + ausgangslage,
                force=True,
            )

        _log_anhaengen(
            projekt_root, "Analyse abgeschlossen - Gerüst gespeichert.",
            laeuft=False, phase="fertig", abgeschlossen=True,
        )
    except OllamaFehler as e:
        _log_anhaengen(projekt_root, f"Fehler: {e}", laeuft=False, fehler=str(e))
    except Exception as e:  # Sicherheitsnetz, analog app/core/automatik.py-Aufrufern
        _log_anhaengen(projekt_root, f"Unerwarteter Fehler: {e}", laeuft=False, fehler=str(e))


@router.post("/analysator/starten", response_model=AnalysatorStartAntwort, status_code=201)
def analysator_starten(anfrage: AnalysatorStartAnfrage, background_tasks: BackgroundTasks,
                        ssh_ziel_id: str | None = None,
                        settings: Settings = Depends(get_settings),
                        benutzer: Benutzer = Depends(get_current_user)):
    epoche_ordner = settings.epochen_dir / anfrage.epoche
    if not epoche_ordner.is_dir():
        raise HTTPException(404, f"Epoche '{anfrage.epoche}' nicht gefunden.")
    epoche_vollstaendig_pruefen(epoche_ordner, anfrage.epoche)
    zweite_epoche_ordner = None
    zweite_epoche_name = anfrage.zweite_epoche.strip() if anfrage.zweite_epoche else None
    if zweite_epoche_name:
        if zweite_epoche_name == anfrage.epoche:
            raise HTTPException(422, "Zweite Epoche muss sich von der ersten unterscheiden.")
        zweite_epoche_ordner = settings.epochen_dir / zweite_epoche_name
        if not zweite_epoche_ordner.is_dir():
            raise HTTPException(404, f"Zweite Epoche '{zweite_epoche_name}' nicht gefunden.")
        epoche_vollstaendig_pruefen(zweite_epoche_ordner, zweite_epoche_name)

    basis_titel = anfrage.titel.strip() or "neu"
    wurzel = projekte_wurzel(settings, benutzer.username)
    ziel = neuer_projekt_pfad(settings, benutzer.username, basis_titel, anfrage.epoche)
    pd.projekt_anlegen(ziel, epoche_ordner, settings.shared_personas_dir, anfrage.epoche,
                        zweite_epoche_ordner, zweite_epoche_name)
    # Rohtext dauerhaft sichern, BEVOR die eigentliche (lang laufende, evtl.
    # fehlschlagende) Analyse angestossen wird - siehe app/core/analysator.py:
    # analyse_speichern. Erst dadurch laesst sich ein Import spaeter erneut
    # anschauen oder nochmal versuchen, ohne den Text erneut einfuegen zu
    # muessen.
    an.analyse_speichern(wurzel, basis_titel, anfrage.text)

    ordner = ziel.relative_to(wurzel).as_posix()
    background_tasks.add_task(_analysieren_lauf, settings, ziel, ssh_ziel_id, anfrage.text)
    return AnalysatorStartAntwort(ordner=ordner)


def _analyse_pfad(settings: Settings, username: str, dateiname: str):
    """Verhindert Path-Traversal, analog app/services.py:projekt_pfad - der
    Dateiname muss eine direkte Datei im (benutzerspezifischen) "Analyse"-
    Ordner sein."""
    ordner = an.analysen_ordner(projekte_wurzel(settings, username)).resolve()
    kandidat = (ordner / dateiname).resolve()
    if ordner not in kandidat.parents:
        raise HTTPException(400, "Ungültiger Dateiname.")
    if not kandidat.is_file():
        raise HTTPException(404, f"Analyse '{dateiname}' nicht gefunden.")
    return kandidat


@router.get("/analysator/analysen", response_model=list[AnalyseEintrag])
def analysen_auflisten(settings: Settings = Depends(get_settings),
                        benutzer: Benutzer = Depends(get_current_user)):
    ordner = an.analysen_ordner(projekte_wurzel(settings, benutzer.username))
    # Nach der ROHEN (sekundengenauen) Zeit sortieren, nicht nach dem auf
    # Minuten gerundeten Anzeige-String - sonst landen zwei innerhalb
    # derselben Minute gespeicherte Analysen in Dateisystem- statt
    # zeitlicher Reihenfolge (stabiler Sort haelt bei gleichem String-
    # Schluessel die urspruengliche glob()-Reihenfolge).
    dateien = sorted(ordner.glob("*.md"), key=lambda d: d.stat().st_ctime, reverse=True)
    ergebnis = []
    for datei in dateien:
        text = pd.lies(datei, pflicht=False, ersatz="")
        ergebnis.append(AnalyseEintrag(
            dateiname=datei.name,
            titel=datei.stem.replace("-", " "),
            erstellt_am=datetime.fromtimestamp(datei.stat().st_ctime).strftime("%Y-%m-%d %H:%M"),
            woerter=woerter(text),
        ))
    return ergebnis


@router.get("/analysator/analysen/{dateiname}", response_class=PlainTextResponse)
def analyse_lesen(dateiname: str, settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    pfad = _analyse_pfad(settings, benutzer.username, dateiname)
    return pfad.read_text(encoding="utf-8")


@router.delete("/analysator/analysen/{dateiname}", status_code=204)
def analyse_loeschen(dateiname: str, settings: Settings = Depends(get_settings),
                      benutzer: Benutzer = Depends(get_current_user)):
    pfad = _analyse_pfad(settings, benutzer.username, dateiname)
    pfad.unlink()


@router.get("/projects/{ordner:path}/analysator-status", response_model=AnalysatorStatusAntwort)
def analysator_status(ordner: str, settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    return AnalysatorStatusAntwort(**an.status_lesen(projekt_root))


@router.post("/analysator/pdf-text", response_model=AnalysatorPdfTextAntwort)
def analysator_pdf_text(datei: UploadFile = File(...), benutzer: Benutzer = Depends(get_current_user)):
    """Liest den Text einer hochgeladenen PDF-Datei (siehe app/core/pdf_text.py)
    und liefert ihn ans Frontend zurueck, das ihn wie eine geladene .txt-Datei
    ins Textfeld des Analysators uebernimmt - der Nutzer sieht und korrigiert
    den Text vor dem Start. Nichts wird gespeichert. Synchron (def), damit
    FastAPI die rechenintensive Extraktion in den Threadpool legt."""
    daten = datei.file.read(pdf_text.MAX_BYTES + 1)
    try:
        ergebnis = pdf_text.pdf_text_extrahieren(daten, an.KAPITEL_STICHWORT_MUSTER)
    except pdf_text.PdfFehler as e:
        raise HTTPException(422, str(e)) from e
    return AnalysatorPdfTextAntwort(
        text=ergebnis.text, seiten=ergebnis.seiten, woerter=woerter(ergebnis.text),
    )


# --- Uebersetzen ins Deutsche (siehe app/core/uebersetzer.py) -----------------

@router.post("/analysator/fuelltext-vorschau", response_model=FuelltextVorschauAntwort)
def fuelltext_vorschau(anfrage: FuelltextVorschauAnfrage, benutzer: Benutzer = Depends(get_current_user)):
    """Vorab-Info fuer die Rueckfrage 'Fuelltext vorher entfernen?': Sprache,
    Zahl und Beispiele der gefundenen Fuelltext-Absaetze (Disclaimer, A/N, ...) und
    die voraussichtliche Zahl der Uebersetzungs-Abschnitte. Kein KI-Aufruf."""
    bereinigt, entfernt = fuelltexte_entfernen(anfrage.text, an.KAPITEL_STICHWORT_MUSTER)
    abschnitte = len(uebs.abschnitte_bilden(bereinigt or anfrage.text))
    return FuelltextVorschauAntwort(
        sprache=sprache_erkennen(anfrage.text),
        woerter=woerter(anfrage.text),
        fuelltext_absaetze=len(entfernt),
        beispiele=[e[:90].replace("\n", " ") for e in entfernt[:6]],
        abschnitte=abschnitte,
        geschaetzte_minuten=abschnitte * uebs.MINUTEN_JE_ABSCHNITT,
    )


async def _chunk_uebersetzen(settings: Settings, base_url: str, absaetze: list[str]) -> list[str]:
    """Uebersetzt EINEN Abschnitt (bis zu 3 Versuche je Aufruf). Stimmt die
    Absatzzahl der Antwort nicht, wird der Abschnitt absatzweise wiederholt."""
    async def aufruf(teile: list[str]) -> str:
        for versuch in range(1, 4):
            try:
                antwort, _meta = await sammle_antwort(
                    base_url, "analysator", uebs.SYSTEM, uebs.user_text(teile),
                    modell_override=rollen_modell_override(settings, "analysator"),
                )
                return uebs.antwort_bereinigen(antwort)
            except OllamaFehler:
                if versuch == 3:
                    raise
                await asyncio.sleep(10)
        return ""

    ergebnis = uebs.absaetze_der_antwort(await aufruf(absaetze))
    if len(ergebnis) == len(absaetze):
        return ergebnis
    einzeln: list[str] = []
    for absatz in absaetze:
        antwort = await aufruf([absatz])
        einzeln.append("\n".join(uebs.absaetze_der_antwort(antwort)) or absatz)
    return einzeln


async def _uebersetzen_lauf(settings: Settings, wurzel, ssh_ziel_id: str | None, text: str,
                             ziel_name: str, fuelltext_entfernen: bool) -> None:
    text_datei = ziel_name[:-4] + ".txt" if ziel_name.endswith(".pdf") else ziel_name
    status = {**uebs.LEERER_STATUS, "log": [], "laeuft": True, "dateiname": ziel_name}

    def schreiben(**felder) -> None:
        status.update(felder)
        status["log"] = status["log"][-200:]
        uebs.status_schreiben(wurzel, status)

    try:
        if fuelltext_entfernen:
            text, entfernt = fuelltexte_entfernen(text, an.KAPITEL_STICHWORT_MUSTER)
            status["fuelltext_entfernt"] = len(entfernt)
            status["log"].append(f"{len(entfernt)} Fülltext-Absatz/Absätze (Disclaimer, A/N, ...) entfernt.")
        abschnitte = uebs.abschnitte_bilden(text)
        if not abschnitte:
            raise ValueError("Es gibt keinen Text zum Übersetzen.")
        trenner = uebs.trenner_fuer(text)
        schreiben(gesamt=len(abschnitte))
        ausgabe = uebs.ergebnis_pfad(wurzel, text_datei)
        ausgabe.write_text("", encoding="utf-8")

        uebersetzt: list[str] = []
        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            for i, abschnitt in enumerate(abschnitte, start=1):
                if uebs.status_lesen(wurzel)["stop_angefordert"]:
                    status["log"].append("Gestoppt - die bisherige Übersetzung bleibt erhalten.")
                    schreiben(gestoppt=True)
                    break
                status["log"].append(f"Übersetze Abschnitt {i} von {len(abschnitte)}...")
                schreiben(aktuell=i)
                uebersetzt.extend(await _chunk_uebersetzen(settings, base_url, abschnitt))
                ergebnis = trenner.join(uebersetzt)
                ausgabe.write_text(ergebnis + "\n", encoding="utf-8")
                schreiben(ergebnis_woerter=woerter(ergebnis))
            else:
                status["log"].append("Übersetzung abgeschlossen.")
                schreiben(abgeschlossen=True)
    except OllamaFehler as e:
        status["log"].append(f"Fehler: {e}")
        schreiben(fehler=str(e))
    except Exception as e:  # Sicherheitsnetz, analog _analysieren_lauf
        status["log"].append(f"Unerwarteter Fehler: {e}")
        schreiben(fehler=str(e))
    finally:
        schreiben(laeuft=False)


@router.post("/analysator/uebersetzen", response_model=UebersetzenStartAntwort, status_code=202)
def uebersetzen_starten(anfrage: UebersetzenStartAnfrage, background_tasks: BackgroundTasks,
                         ssh_ziel_id: str | None = Query(None),
                         settings: Settings = Depends(get_settings),
                         benutzer: Benutzer = Depends(get_current_user)):
    wurzel = projekte_wurzel(settings, benutzer.username)
    if uebs.status_lesen(wurzel)["laeuft"]:
        raise HTTPException(409, "Es läuft bereits eine Übersetzung.")
    ziel_name = uebs.dateiname_de(anfrage.dateiname)
    # Sofort als "laeuft" markieren (nicht erst im Hintergrund-Task), damit ein
    # zweiter Start in derselben Sekunde ebenfalls abgewiesen wird.
    uebs.status_schreiben(
        wurzel, {**uebs.LEERER_STATUS, "log": ["Startet..."], "laeuft": True, "dateiname": ziel_name},
        behalte_stop=False,
    )
    background_tasks.add_task(
        _uebersetzen_lauf, settings, wurzel, ssh_ziel_id, anfrage.text, ziel_name, anfrage.fuelltext_entfernen,
    )
    return UebersetzenStartAntwort(dateiname=ziel_name)


@router.get("/analysator/uebersetzen/status", response_model=UebersetzenStatusAntwort)
def uebersetzen_status(settings: Settings = Depends(get_settings), benutzer: Benutzer = Depends(get_current_user)):
    return UebersetzenStatusAntwort(**uebs.status_lesen(projekte_wurzel(settings, benutzer.username)))


@router.post("/analysator/uebersetzen/stop")
def uebersetzen_stop(settings: Settings = Depends(get_settings), benutzer: Benutzer = Depends(get_current_user)):
    wurzel = projekte_wurzel(settings, benutzer.username)
    status = uebs.status_lesen(wurzel)
    if status["laeuft"]:
        status["stop_angefordert"] = True
        uebs.status_schreiben(wurzel, status)
    return {"stop_angefordert": True}


def _ergebnis_text(settings: Settings, benutzer: Benutzer) -> tuple[str, str]:
    wurzel = projekte_wurzel(settings, benutzer.username)
    name = uebs.status_lesen(wurzel)["dateiname"]
    if not name:
        raise HTTPException(404, "Es gibt noch keine Übersetzung.")
    text_datei = name[:-4] + ".txt" if name.endswith(".pdf") else name
    pfad = uebs.ergebnis_pfad(wurzel, text_datei)
    if not pfad.is_file():
        raise HTTPException(404, "Das Ergebnis der Übersetzung wurde nicht gefunden.")
    return name, pfad.read_text(encoding="utf-8")


@router.get("/analysator/uebersetzen/ergebnis", response_class=PlainTextResponse)
def uebersetzen_ergebnis(settings: Settings = Depends(get_settings), benutzer: Benutzer = Depends(get_current_user)):
    return _ergebnis_text(settings, benutzer)[1]


@router.get("/analysator/uebersetzen/pdf")
def uebersetzen_pdf(settings: Settings = Depends(get_settings), benutzer: Benutzer = Depends(get_current_user)):
    name, text = _ergebnis_text(settings, benutzer)
    pdf = uebs.text_pdf_erzeugen(name.rsplit(".", 1)[0].replace("_", " "), text)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/analysator/epoche-vorschlagen", response_model=EpocheVorschlagAntwortLLM)
async def analysator_epoche_vorschlagen(anfrage: AnalysatorEpocheVorschlagAnfrage,
                                         ssh_ziel_id: str | None = Query(None),
                                         settings: Settings = Depends(get_settings),
                                         benutzer: Benutzer = Depends(get_current_user)):
    """Dritter, eigenstaendiger Analysator-Weg neben "starten" (siehe ToDo.md
    "erweitere den Analysator"): EIN kurzer, nicht-dialogischer Ollama-
    Aufruf (kein Hintergrund-Task noetig, anders als die volle Kapitel-
    Analyse) leitet aus dem importierten Text ein Epoche-Formular-Vorschlag
    ab - dieselben Felder wie EpocheErstellenAnfrage/app/core/epoche.py:
    EpocheAntworten. Erzeugt NOCH KEINE Epoche - der Nutzer prueft/
    bearbeitet den Vorschlag im Frontend, bevor er ueber das bereits
    bestehende POST /api/epochen (app/api/epochen.py) tatsaechlich
    gespeichert wird. Bewusst nur ein knapper Auszug (nicht der komplette,
    ggf. sehr lange Text) als Kontext - das Setting laesst sich aus Anfang/
    Ende meist zuverlaessig genug ableiten, und ein schneller Aufruf ist
    hier wichtiger als vollstaendige Abdeckung (der Nutzer bearbeitet das
    Ergebnis ohnehin von Hand nach)."""
    persona = pd.lies(settings.shared_personas_dir / "analysator.txt")
    system = an.epoche_vorschlag_system(persona)
    bereinigt, _entfernt = fuelltexte_entfernen(anfrage.text)
    user = an.epoche_vorschlag_user(
        an.textauszug_bauen(bereinigt, woerter_anfang=700, woerter_ende=400), sprache_erkennen(bereinigt),
    )
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        try:
            antwort_text, _meta = await sammle_antwort(
                base_url, "analysator", system, user, format="json",
                modell_override=rollen_modell_override(settings, "analysator"),
            )
        except OllamaFehler as e:
            raise HTTPException(502, str(e)) from e
    try:
        vorschlag = EpocheVorschlagAntwortLLM.model_validate_json(antwort_text)
    except ValidationError as e:
        raise HTTPException(502, f"Antwort der KI konnte nicht gelesen werden: {e}") from e

    # Sicherheitsnetz: der FanFic-Hinweis (app/core/epoche.py:
    # einleitungssatz_vorlage) greift nur bei erfunden=True - ein Vorschlag,
    # der ein Franchise nennt, MUSS deshalb konsistent auch erfunden=True
    # setzen, unabhaengig davon, ob das Modell das selbst korrekt verknuepft.
    if vorschlag.vorbild_franchise.strip():
        vorschlag.erfunden = True
    return vorschlag
