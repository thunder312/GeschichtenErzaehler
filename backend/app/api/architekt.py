"""Architekten-Interview: geführtes Mehrschritt-Gespräch statt Rohtext-
Editor. Portiert aus pre-GUI/novelle.py cmd_architekt() (siehe
app/core/architekt.py für die reine Filter-/Erkennungslogik).

Ablauf, identisch zum CLI:
1. Gespraech startet automatisch mit "Lass uns anfangen. Stelle mir die
   ersten Fragen." als erster (interner) Eingabe.
2. Bei jedem Zug wird der KOMPLETTE bisherige Verlauf als eine User-
   Nachricht an die Rolle 'architekt' geschickt, die Antwort auf die erste
   gestellte Frage gekuerzt (falls das Modell mehrere auf einmal stellt).
3. Sobald eine Antwort mit '# STORY-GERUEST' beginnt, ist das Gespraech
   abgeschlossen: geruest.md wird gespeichert, eine erkannte Ausgangslage
   als stand_00.md, und der Projektordner ggf. nach dem gewaehlten Titel
   umbenannt (nur falls noch kein Kapitel existiert).

Unterschied zum CLI: Denk-Tokens (still=True-Aequivalent) werden nicht live
gestreamt - nur ein "denkt nach"-Signal - weil sonst mehrere Fragen kurz
sichtbar waeren, bevor der Ein-Frage-Filter greift (siehe cmd_architekt-
Kommentar im Original).

Zwischenspeichern/Fortsetzen: der Verlauf wird nach jedem Zug als
architekt_verlauf.json im Projekt abgelegt (siehe pd.architekt_verlauf_datei)
und erst bei Abschluss oder explizitem Abbruch ("ende"/"exit"/"quit")
wieder geloescht. Trennt die Verbindung stattdessen unerwartet (Tab
geschlossen, Netzwerk weg) oder schliesst das Frontend sie bewusst zum
Pausieren, bleibt die Datei liegen - der naechste Verbindungsaufbau zu
diesem Projekt erkennt sie und setzt das Gespraech an genau der Stelle
fort, sendet dafuer aber zuerst den kompletten bisherigen Verlauf ans
Frontend, damit der Chat-Verlauf dort nicht bei der letzten Frage leer
anfaengt.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.auth import get_current_user, get_current_user_ws
from app.config import Settings, get_settings
from app.core import architekt as arch
from app.core import fundus as fu
from app.core import geruest as g
from app.core import projekt_dateien as pd
from app.core.fundus_schema import FundusExtraktionAntwortLLM
from app.core.ollama_client import OllamaFehler, chat_stream, sammle_antwort
from app.core.rollen import ROLLEN
from app.schemas import Benutzer, HandlungstextAnfrage
from app.services import fundus_datei, ollama_basis_url, ordner_nach_umbenennung, projekt_pfad, rollen_modell_override

router = APIRouter(prefix="/api/projects", tags=["architekt"])

ERSTE_EINGABE = "Lass uns anfangen. Stelle mir die ersten Fragen."


def _verlauf_laden(projekt_root) -> list[str] | None:
    datei = pd.architekt_verlauf_datei(projekt_root / "projekt")
    if not datei.exists():
        return None
    try:
        verlauf = json.loads(datei.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return verlauf or None


def _verlauf_speichern(projekt_root, verlauf: list[str]) -> None:
    datei = pd.architekt_verlauf_datei(projekt_root / "projekt")
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps(verlauf, ensure_ascii=False, indent=2), encoding="utf-8")


def _verlauf_loeschen(projekt_root) -> None:
    pd.architekt_verlauf_datei(projekt_root / "projekt").unlink(missing_ok=True)


@router.get("/{ordner:path}/architekt-fortsetzbar")
def architekt_fortsetzbar(ordner: str, settings: Settings = Depends(get_settings),
                           benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    return {"fortsetzbar": _verlauf_laden(projekt_root) is not None}


@router.get("/{ordner:path}/architekt-vorlage")
def architekt_vorlage(ordner: str, settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    """Liefert ein ausfuellbares Vorlage-Dokument fuer dieses Projekt zum
    Offline-Vorbereiten des Architekten-Interviews (siehe
    arch.vorlage_erzeugen und ArchitektInterviewPage.tsx) - basiert auf der
    Epoche-Persona des Projekts, damit die Platzhaltertexte zur tatsaechlich
    gewaehlten Epoche passen."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    persona_text = pd.persona_lesen(projekt_root, "architekt")
    return {"vorlage": arch.vorlage_erzeugen(persona_text)}


@router.post("/{ordner:path}/architekt-extraktion")
async def architekt_extraktion(ordner: str, anfrage: HandlungstextAnfrage,
                                ssh_ziel_id: str | None = Query(None),
                                settings: Settings = Depends(get_settings),
                                benutzer: Benutzer = Depends(get_current_user)):
    """Dritter Weg zu einem Story-Gerüst (neben gefuehrtem Interview und von
    Hand ausgefuellter Vorlage): extrahiert per einmaligem, nicht-
    dialogischem LLM-Aufruf einen Vorlage-Entwurf aus einem importierten
    Handlungstext (siehe arch.handlungstext_extraktion_system). Antwortform
    bewusst identisch zu architekt_vorlage() ({"vorlage": ...}), damit das
    Frontend den Entwurf in dieselbe editierbare Vorlage-Textarea laedt -
    der Nutzer prueft/bestaetigt ihn dort, bevor er wie gewohnt ueber
    erste_eingabe_mit_vorlage() ins Interview startet."""
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    persona_text = pd.persona_lesen(projekt_root, "architekt")
    system = arch.handlungstext_extraktion_system(persona_text)
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        try:
            antwort, _meta = await sammle_antwort(
                base_url, "architekt", system, anfrage.handlungstext.strip(),
                modell_override=rollen_modell_override(settings, "architekt"),
            )
        except OllamaFehler as e:
            raise HTTPException(502, str(e)) from e
    return {"vorlage": antwort}


def _fundus_kontext(settings: Settings, benutzer: Benutzer, projekt_root) -> str:
    """Baut den einmalig an persona_text anzuhaengenden Fundus-Auszug fuer
    die aktuelle Epoche des Projekts (siehe app/core/fundus.py) - leerer
    String, falls das Projekt keine Epoche hat oder der Fundus dafuer noch
    keinen Abschnitt enthaelt."""
    epoche = pd.epoche_von_projekt(projekt_root)
    if not epoche:
        return ""
    fundus_text = pd.lies(fundus_datei(settings, benutzer.username), pflicht=False, ersatz="")
    abschnitt = fu.epoche_abschnitt_erkennen(fundus_text, epoche) if fundus_text else None
    if not abschnitt:
        return ""
    return f"\n\n## FUNDUS DIESER EPOCHE\n{abschnitt}\n"


async def _fundus_aktualisieren(settings: Settings, benutzer: Benutzer, projekt_root, base_url: str,
                                 geruest_text: str) -> None:
    """Extrahiert Figuren aus dem fertigen Geruest und fuehrt sie in den
    Personen-Fundus des Nutzers ein (siehe app/core/fundus.py). Rein additiv
    und bewusst NICHT-FATAL: jeder Fehler hier darf den erfolgreichen
    Abschluss des Architekten-Interviews nicht verhindern, das Geruest ist
    zu diesem Zeitpunkt bereits gespeichert."""
    figuren_text = arch.figuren_abschnitt_erkennen(geruest_text)
    if not figuren_text:
        return
    epoche = pd.epoche_von_projekt(projekt_root)
    if not epoche:
        return

    try:
        persona = pd.lies(settings.shared_personas_dir / "fundus_pfleger.txt")
        antwort_text, _ = await sammle_antwort(
            base_url, "fundus_pfleger", persona, figuren_text, format="json",
            modell_override=rollen_modell_override(settings, "fundus_pfleger"),
        )
        antwort = FundusExtraktionAntwortLLM.model_validate_json(antwort_text)
    except (OllamaFehler, ValidationError):
        return
    if not antwort.figuren:
        return

    titel = g.titel_erkennen(geruest_text) or projekt_root.name
    figuren = [fu.FigurEintrag(name=e.name, alter=e.alter, stand=e.stand, eigenschaften=e.eigenschaften)
               for e in antwort.figuren]
    ziel = fundus_datei(settings, benutzer.username)
    fundus_text = pd.lies(ziel, pflicht=False, ersatz=fu.leere_vorlage())
    fundus_text = fu.figuren_zusammenfuehren(fundus_text, epoche, titel, figuren)
    pd.schreib(ziel, fundus_text, force=True)


_MAX_GERUEST_VERSUCHE = 2


async def _einen_zug_generieren(base_url: str, settings: Settings, persona_text: str,
                                 verlauf: list[str], websocket: WebSocket,
                                 ueberschreibe: dict | None) -> str:
    teile: list[str] = []
    async for event in chat_stream(
        base_url, "architekt", persona_text, arch.verlauf_zu_text(verlauf),
        ueberschreibe=ueberschreibe,
        modell_override=rollen_modell_override(settings, "architekt"),
    ):
        if event.typ == "error":
            await websocket.send_json({"phase": "fehler", "typ": "error", "text": event.text})
            raise OllamaFehler(event.text)
        if event.typ == "thinking":
            await websocket.send_json({"phase": "frage", "typ": "denkt_nach"})
        if event.typ == "content":
            teile.append(event.text)
    return "".join(teile).strip()


async def _zug(websocket: WebSocket, settings: Settings, base_url: str, persona_text: str,
                verlauf: list[str]) -> tuple[str, bool]:
    """verlauf muss bereits mit der aktuellen "Ich: ..."-Zeile enden (siehe
    Aufrufer in ws_architekt) - _zug() haengt hier nur noch die Antwort
    ("Du: ...") an. Der Aufrufer haengt bewusst VORHER an, nicht hier: beim
    "zurueckgesetzt"-Zweig (Schritte zurueckgehen) muss die neue eigene
    Antwort schon im an das Frontend gesendeten Verlauf stehen, bevor
    ueberhaupt ein neuer Zug beginnt (siehe ArchitektInterviewPage.tsx-
    Kommentar zu "zurueckgesetzt": der Verlauf muss dort mit der gerade
    bearbeiteten eigenen Antwort enden)."""
    await websocket.send_json({"phase": "frage", "typ": "start"})

    # Ein fertiges Geruest MUSS einen auswertbaren Kapitelplan enthalten -
    # Automatikmodus und letztes_geplantes_kapitel() bauen direkt darauf auf
    # (siehe app/core/geruest.py). Wird die Antwort durch die num_predict-
    # Grenze abgeschnitten, bevor der Kapitelplan geschrieben wurde, kam
    # bisher trotzdem "# STORY-GERUEST..." als Praefix durch und wurde
    # klaglos als abgeschlossen gespeichert - ein Projekt blieb dauerhaft
    # ohne Kapitelplan zurueck (siehe Vorfall
    # "Der-Preis-der-Wuerde-Ein-Geheimnis-in-Mayfair"). Ein Retry mit
    # verdoppeltem num_predict behebt die meisten Faelle automatisch, ohne
    # dass der Nutzer davon etwas mitbekommt.
    ueberschreibe: dict | None = None
    antwort = ""
    for versuch in range(1, _MAX_GERUEST_VERSUCHE + 1):
        antwort = await _einen_zug_generieren(base_url, settings, persona_text, verlauf, websocket, ueberschreibe)
        ist_geruest = arch.ist_geruest_antwort(antwort)
        if not ist_geruest or g.kapitelplan_erkennen(antwort):
            break
        if versuch < _MAX_GERUEST_VERSUCHE:
            ueberschreibe = {"num_predict": ROLLEN["architekt"]["optionen"]["num_predict"] * 2}

    if ist_geruest and not g.kapitelplan_erkennen(antwort):
        fehlertext = (
            "Die Antwort des Architekten wurde wiederholt abgeschnitten und "
            "enthielt keinen vollständigen Kapitelplan. Bitte versuche es "
            "erneut - ggf. hilft eine kürzere Vorgabe bei der Kapitel-Frage."
        )
        await websocket.send_json({"phase": "fehler", "typ": "error", "text": fehlertext})
        raise OllamaFehler(fehlertext)

    if not ist_geruest:
        antwort = arch.nur_erste_frage(antwort)
    verlauf.append(f"Du: {antwort}")
    return antwort, ist_geruest


@router.websocket("/{ordner:path}/ws/architekt")
async def ws_architekt(websocket: WebSocket, ordner: str, ssh_ziel_id: str | None = None,
                        benutzer: Benutzer = Depends(get_current_user_ws),
                        settings: Settings = Depends(get_settings)):
    # settings MUSS per Depends() kommen, nicht per direktem get_settings()-
    # Aufruf: FastAPIs app.dependency_overrides (siehe Tests) greift nur bei
    # per Depends() aufgeloesten Parametern - ein direkter Aufruf umgeht das
    # und lieferte in Tests unbemerkt die echten Produktiv-Settings statt der
    # tmp_path-Test-Settings (Symptom: "Projekt 'X' nicht gefunden", obwohl
    # das Projekt gerade erst ueber denselben TestClient angelegt wurde).
    await websocket.accept()
    try:
        projekt_root = projekt_pfad(settings, benutzer.username, ordner)
        persona_text = pd.persona_lesen(projekt_root, "architekt") + _fundus_kontext(settings, benutzer, projekt_root)

        gespeicherter_verlauf = _verlauf_laden(projekt_root)

        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            if gespeicherter_verlauf is not None:
                verlauf = gespeicherter_verlauf
                # Der Verlauf endet immer mit "Du: <letzte gestellte Frage>"
                # (siehe _zug) - ein bereits abgeschlossenes Geruest wuerde
                # sofort gespeichert und die Verlaufsdatei geloescht, kann
                # hier also nicht vorkommen.
                antwort = verlauf[-1].removeprefix("Du: ")
                fertig = False
                await websocket.send_json({"phase": "fortgesetzt", "verlauf": verlauf})
            else:
                verlauf = []
                # Bei einem frischen Start (kein gespeicherter Verlauf)
                # wartet das Frontend absichtlich mit dem ersten Zug, bis es
                # eine Initialnachricht geschickt hat (siehe
                # ArchitektInterviewPage.tsx:starten) - so kann optional ein
                # offline ausgefuelltes Vorlage-Dokument mitgegeben werden
                # (siehe arch.erste_eingabe_mit_vorlage). Beim Fortsetzen
                # eines gespeicherten Gespraechs (Zweig oben) entfaellt das,
                # da dort die naechste Nachricht bereits die Antwort auf die
                # letzte offene Frage ist.
                erste_nachricht = await websocket.receive_json()
                vorlage_text = (erste_nachricht.get("vorlage_text") or "").strip()
                eingabe = arch.erste_eingabe_mit_vorlage(vorlage_text) if vorlage_text else ERSTE_EINGABE
                verlauf.append(f"Ich: {eingabe}")
                antwort, fertig = await _zug(websocket, settings, base_url, persona_text, verlauf)
                _verlauf_speichern(projekt_root, verlauf)

            while True:
                if fertig:
                    _, gesichert_als = pd.schreib(pd.geruest_datei(projekt_root / "projekt"), antwort, force=True)
                    await _fundus_aktualisieren(settings, benutzer, projekt_root, base_url, antwort)
                    ausgangslage = arch.ausgangslage_erkennen(antwort)
                    ausgangslage_gespeichert = False
                    if ausgangslage:
                        pd.schreib(
                            pd.stand_datei(projekt_root / "projekt", 0),
                            "# STAND VOR KAPITEL EINS\n\n" + ausgangslage,
                            force=True,
                        )
                        ausgangslage_gespeichert = True

                    pd.schreib(
                        projekt_root / "projekt" / "architekten_gespraech.md",
                        arch.transkript_erzeugen(verlauf),
                        force=True,
                    )

                    neuer_name = pd.projektordner_umbenennen(projekt_root, antwort)
                    neuer_ordner = ordner_nach_umbenennung(ordner, neuer_name) if neuer_name else ordner

                    _verlauf_loeschen(projekt_root)
                    await websocket.send_json({
                        "phase": "abgeschlossen",
                        "geruest": antwort,
                        "ausgangslage_gespeichert": ausgangslage_gespeichert,
                        "gesichert_als": gesichert_als,
                        "neuer_ordner": neuer_ordner,
                        "kapitelplan_platzhalter": g.kapitelplan_platzhalter_erkennen(antwort),
                    })
                    break

                await websocket.send_json({"phase": "frage", "typ": "fertig", "text": antwort})

                nachricht = await websocket.receive_json()
                eingabe = (nachricht.get("eingabe") or "").strip()
                bearbeite_ab = nachricht.get("bearbeite_ab")

                if bearbeite_ab is not None:
                    # Nutzer bearbeitet eine FRUEHERE eigene Antwort (siehe
                    # ArchitektInterviewPage.tsx) statt die aktuell offene
                    # Frage zu beantworten - "Schritte zurueckgehen" ist hier
                    # kein eigener Zustand, sondern schlicht: verlauf auf den
                    # Stand VOR der bearbeiteten Antwort zurueckstutzen (siehe
                    # arch.verlauf_gekuerzt_ab) und mit dem neuen Text genau
                    # wie eine normale Antwort weiterfuehren.
                    gekuerzt = eingabe and arch.verlauf_gekuerzt_ab(verlauf, bearbeite_ab)
                    if not gekuerzt:
                        await websocket.send_json({
                            "phase": "fehler", "typ": "error",
                            "text": "Ungültiger Bearbeitungsversuch - bitte Seite neu laden.",
                        })
                        break
                    verlauf[:] = gekuerzt
                    verlauf.append(f"Ich: {eingabe}")
                    await websocket.send_json({"phase": "zurueckgesetzt", "verlauf": list(verlauf)})
                elif not eingabe or eingabe.lower() in ("ende", "exit", "quit"):
                    _verlauf_loeschen(projekt_root)
                    await websocket.send_json({"phase": "beendet_ohne_speichern"})
                    break
                else:
                    verlauf.append(f"Ich: {eingabe}")

                antwort, fertig = await _zug(websocket, settings, base_url, persona_text, verlauf)
                _verlauf_speichern(projekt_root, verlauf)

    except OllamaFehler:
        pass
    except WebSocketDisconnect:
        # Verbindung unerwartet weg (Tab geschlossen, Netzwerk) oder vom
        # Frontend bewusst zum Pausieren geschlossen - der zuletzt
        # gespeicherte Verlauf (siehe _verlauf_speichern oben) bleibt
        # bewusst liegen, damit die naechste Verbindung zu diesem Projekt
        # das Gespraech fortsetzen kann.
        return
    except Exception as e:
        # Sicherheitsnetz gegen unerwartete Fehler - siehe gleiches Muster
        # in app/api/pipeline.py:ws_schreiben.
        try:
            await websocket.send_json({"phase": "fehler", "typ": "error", "text": str(e)})
        except RuntimeError:
            pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
