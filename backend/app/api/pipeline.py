"""Die eigentlichen Pipeline-Schritte: Schreiben (WebSocket, streamend),
Pruefen, Anwenden, Lektorieren, Stand, Export/Zusammenfassen,
Rechtschreibpruefung.

Portiert aus pre-GUI/novelle.py (cmd_schreiben, _pruefe, cmd_anwenden,
cmd_lektorieren, cmd_stand, cmd_export, cmd_zusammenfassen,
cmd_rechtschreibung) - Prompt-Aufbau und Reihenfolge der Nachbearbeitungs-
Schritte sind bewusst wortgleich zum Original, damit dieselbe Geschichte in
CLI und GUI gleich behandelt wird (siehe doc/Schnittstellen-Uebersicht.md).

Automatische Fortsetzung bei zu kurzen Kapiteln (Abschnitt 5.5) ist in
dieser ersten Fassung noch NICHT implementiert - der Standardfall
(Fortsetzung deaktiviert) verhaelt sich bereits identisch: Es wird nur ein
Hinweis zurueckgegeben, das Kapitel bleibt unveraendert kurz.
"""
from __future__ import annotations

import functools
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect

from app.config import Settings, get_settings
from app.core import geruest as g
from app.core import heuristik as h
from app.core import projekt_dateien as pd
from app.core import ssh_manager
from app.core.ollama_client import OllamaFehler, chat_stream
from app.core.pdf_export import buch_pdf_erzeugen
from app.core.rollen import ROLLEN, STUFE_DIREKTIVEN
from app.core.textutil import woerter
from app.schemas import AnwendenAntwort, BefundeAntwort, RechtschreibAntwort, RechtschreibWort
from app.services import ollama_basis_url, projekt_pfad, ssh_ziel_aus_db

router = APIRouter(prefix="/api/projects", tags=["pipeline"])

KUERZUNGS_SCHWELLE = 0.7  # Kuerzungs-Waechter: unter 70% des Originals -> nicht automatisch uebernehmen


async def _sammle_stream(base_url: str, rolle: str, system: str, user: str) -> tuple[str, dict]:
    text = ""
    meta: dict = {}
    async for event in chat_stream(base_url, rolle, system, user):
        if event.typ == "error":
            raise HTTPException(502, f"Ollama-Fehler ({rolle}): {event.text}")
        if event.typ == "done":
            text, meta = event.text, event.meta
    if not text:
        raise HTTPException(502, f"Leere Antwort von Rolle '{rolle}' erhalten.")
    return text, meta


async def _pruefe_kapitel(projekt: Path, base_url: str, n: int, kapiteltext: str) -> str:
    geruest_text = pd.lies(pd.geruest_datei(projekt))
    verbote = pd.lies(pd.verbotsliste_datei(projekt), pflicht=False, ersatz="")
    vorher = pd.lies(pd.stand_datei(projekt, n - 1), pflicht=False,
                      ersatz="(Kein vorheriger Stand vorhanden. Dies ist das erste Kapitel.)")
    jahr = g.jahr_erkennen(geruest_text)

    anachronismen, _ = await _sammle_stream(
        base_url, "anachronismus", pd.persona_lesen(projekt.parent, "pruefer_anachronismus"),
        f"JAHR: {jahr}\n\n=== VERBOTSLISTE ===\n{verbote}\n\n=== KAPITELTEXT ===\n{kapiteltext}",
    )
    kontinuitaet, _ = await _sammle_stream(
        base_url, "kontinuitaet", pd.persona_lesen(projekt.parent, "pruefer_kontinuitaet"),
        f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n=== NEUES KAPITEL {n} ===\n{kapiteltext}",
    )

    bericht = (
        f"# Befunde zu Kapitel {n}\n\n"
        f"Erzeugt: {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"Jahr laut Geruest: {jahr}\n\n"
        f"---\n\n## Anachronismen\n\n{anachronismen}\n\n"
        f"---\n\n## Kontinuitaet und Logik\n\n{kontinuitaet}\n"
    )
    pd.schreib(pd.befunde_datei(projekt, n), bericht)
    return bericht


async def _stand_ausfuehren(projekt_root: Path, base_url: str, n: int) -> tuple[str, bool]:
    projekt = projekt_root / "projekt"
    kapiteltext = pd.lies(pd.kapitel_datei(projekt, n))
    vorher = pd.lies(pd.stand_datei(projekt, n - 1), pflicht=False,
                      ersatz="(Kein vorheriger Stand vorhanden.)")
    text, _ = await _sammle_stream(
        base_url, "chronist", pd.persona_lesen(projekt_root, "chronist"),
        f"=== BISHERIGER STAND ===\n{vorher}\n\n=== KAPITEL {n} ===\n{kapiteltext}\n\n"
        f"=== AUFTRAG ===\nAktualisiere den Stand auf Kapitel {n}.",
    )
    pd.schreib(pd.stand_datei(projekt, n), text)

    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
    letztes = g.letztes_geplantes_kapitel(geruest_text) if geruest_text else None
    vorhandene = pd.vorhandene_kapitel(projekt)
    auto_export = bool(letztes and n == letztes and len(vorhandene) >= letztes)
    if auto_export:
        _export_ausfuehren(projekt)
    return text, auto_export


def _export_ausfuehren(projekt: Path) -> str:
    kapitel = pd.vorhandene_kapitel(projekt)
    if not kapitel:
        raise HTTPException(404, "Keine Kapitel gefunden.")
    ganz = "\n\n".join(pd.lies(p) for p in kapitel)
    pd.schreib(projekt / "gesamt.md", ganz, force=True)
    return ganz


@router.websocket("/{ordner:path}/ws/schreiben/{n}")
async def ws_schreiben(websocket: WebSocket, ordner: str, n: int,
                        zusatzhinweis: str = "", ssh_ziel_id: str | None = None):
    settings = get_settings()
    await websocket.accept()
    try:
        projekt_root = projekt_pfad(settings, ordner)
        projekt = projekt_root / "projekt"

        # Stand-Sicherstellung (siehe Schnittstellen-Uebersicht 5.14): fehlt
        # stand_(n-1).md, aber Kapitel n-1 existiert, wird er zuerst nachgeholt.
        if n > 1 and not pd.stand_datei(projekt, n - 1).exists():
            if not pd.kapitel_datei(projekt, n - 1).exists():
                await websocket.send_json({
                    "phase": "fehler", "typ": "error",
                    "text": f"Weder stand_{n-1:02d}.md noch kapitel_{n-1:02d}.md "
                            f"vorhanden - Kapitel muessen der Reihe nach geschrieben werden.",
                })
                await websocket.close()
                return

        geruest_text = pd.lies(pd.geruest_datei(projekt))
        stufe = g.jugendschutz_stufe_erkennen(geruest_text)
        autor_rolle = g.autor_rolle_erkennen(geruest_text)
        ziel = g.kapitelplan_erkennen(geruest_text).get(n)
        kapitel_block = g.kapitel_block_erkennen(geruest_text, n)
        vorher = pd.lies(pd.stand_datei(projekt, n - 1), pflicht=False,
                          ersatz="(Kein vorheriger Stand. Dies ist das erste Kapitel.)")

        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            if n > 1 and not pd.stand_datei(projekt, n - 1).exists() \
                    and pd.kapitel_datei(projekt, n - 1).exists():
                await websocket.send_json({"phase": "stand_nachholen", "typ": "start", "kapitel": n - 1})
                await _stand_ausfuehren(projekt_root, base_url, n - 1)
                await websocket.send_json({"phase": "stand_nachholen", "typ": "done", "kapitel": n - 1})
                vorher = pd.lies(pd.stand_datei(projekt, n - 1))

            zielsatz = f"Zielumfang: etwa {ziel} Woerter." if ziel else ""
            aktueller_hinweis = (
                f"\n\n=== NUR DIESES KAPITEL SCHREIBEN (Kapitel {n}) ===\n{kapitel_block}\n\n"
                f"Bleibe ausschliesslich in der oben fuer DIESES Kapitel beschriebenen "
                f"Stufe der Liebeshandlung. Verwende KEINE Ereignisse, keine Explizitheit "
                f"und keinen Beziehungsstand aus einem ANDEREN Kapitel des Gesamtplans."
                if kapitel_block else ""
            )
            zusatz_block = (
                f"\n\n=== ZUSAETZLICHER HINWEIS FUER DIESEN VERSUCH ===\n{zusatzhinweis}\n"
                f"Dieser Hinweis gilt nur fuer diesen einen Schreibversuch und hat "
                f"Vorrang, falls er einem Detail des Geruests widerspricht."
                if zusatzhinweis else ""
            )
            user_prompt = (
                f"=== STORY-GERUEST ===\n{geruest_text}\n\n"
                f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
                f"=== AUFTRAG ===\nSchreibe Kapitel {n}. {zielsatz}\n"
                f"Gib ausschliesslich den Kapiteltext aus.\n\n"
                f"{STUFE_DIREKTIVEN[stufe]}{aktueller_hinweis}{zusatz_block}"
            )

            teile: list[str] = []
            await websocket.send_json({
                "phase": "autor", "typ": "start",
                "modell": ROLLEN[autor_rolle]["modell"], "ziel_woerter": ziel,
            })
            async for event in chat_stream(base_url, autor_rolle, pd.persona_lesen(projekt_root, "autor"), user_prompt):
                if event.typ == "error":
                    await websocket.send_json({"phase": "autor", "typ": "error", "text": event.text})
                    await websocket.close()
                    return
                if event.typ in ("thinking", "content"):
                    teile.append(event.text) if event.typ == "content" else None
                    await websocket.send_json({"phase": "autor", "typ": event.typ, "text": event.text})
                if event.typ == "done":
                    await websocket.send_json({"phase": "autor", "typ": "done", "meta": event.meta})

            text = "".join(teile).strip()
            text, findings_neustart = h.kapitel_neustart_abschneiden(text)
            text, findings_ende = h.vorzeitige_kapitelende_abschneiden(text)
            findings = findings_neustart + findings_ende

            if ziel and not g.automatische_fortsetzung_aktiviert(geruest_text) \
                    and woerter(text) < ziel * 0.70:
                findings.append(h.Finding(
                    "zu_kurz",
                    f"Kapitel {n} liegt bei {woerter(text)} von {ziel} Woertern "
                    f"({woerter(text)/ziel:.0%}). Automatische Fortsetzung ist "
                    f"deaktiviert - Kapitel bleibt so, wie es ist.",
                    schwere="info",
                ))

            titelseite_hinzugefuegt = False
            if n == 1:
                epoche = pd.epoche_von_projekt(projekt_root)
                titelseite = g.titelseite_erzeugen(geruest_text, epoche)
                if titelseite:
                    erste_zeile = titelseite.strip().split("\n")[0]
                    if not text.lstrip().startswith(erste_zeile):
                        text = titelseite + text
                        titelseite_hinzugefuegt = True

            _, gesichert_als = pd.schreib(pd.kapitel_datei(projekt, n), text)

            if ziel:
                ist = woerter(text)
                abw = (ist - ziel) / ziel * 100
                if abs(abw) > 25:
                    findings.append(h.Finding(
                        "umfang_abweichung",
                        f"Umfang weicht deutlich ab: {ist} statt {ziel} Woerter ({abw:+.0f} %).",
                    ))

            findings += h.alle_nachbearbeitungs_checks(text, geruest_text, stufe)

            unbekannt = h.hunspell_unbekannte_woerter(
                text, exec_fn=_hunspell_exec_fn(settings, ssh_ziel_id),
            )
            if unbekannt:
                findings.append(h.Finding(
                    "rechtschreibung",
                    f"hunspell kennt folgende Woerter nicht (Eigennamen, "
                    f"Fachbegriffe oder Tippfehler): {', '.join(unbekannt)}",
                    schwere="info",
                ))

            await websocket.send_json({
                "phase": "nachbearbeitung", "typ": "done",
                "findings": [f.__dict__ for f in findings],
                "gesichert_als": gesichert_als,
                "titelseite_hinzugefuegt": titelseite_hinzugefuegt,
            })

            await websocket.send_json({"phase": "pruefen", "typ": "start"})
            befunde_text = await _pruefe_kapitel(projekt, base_url, n, text)
            await websocket.send_json({"phase": "pruefen", "typ": "done", "text": befunde_text})

            await websocket.send_json({"phase": "abgeschlossen", "kapitel_text": text})

    except OllamaFehler as e:
        await websocket.send_json({"phase": "fehler", "typ": "error", "text": str(e)})
    except HTTPException as e:
        await websocket.send_json({"phase": "fehler", "typ": "error", "text": e.detail})
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


def _hunspell_exec_fn(settings: Settings, ssh_ziel_id: str | None):
    if not ssh_ziel_id:
        return None
    ziel = ssh_ziel_aus_db(settings, ssh_ziel_id)
    return functools.partial(ssh_manager.exec_command, ziel)


@router.post("/{ordner:path}/pruefen/{n}", response_model=BefundeAntwort)
async def pruefen(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                   settings: Settings = Depends(get_settings)):
    projekt_root = projekt_pfad(settings, ordner)
    projekt = projekt_root / "projekt"
    kapiteltext = pd.lies(pd.kapitel_datei(projekt, n))
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        bericht = await _pruefe_kapitel(projekt, base_url, n, kapiteltext)
    return BefundeAntwort(kapitel=n, inhalt=bericht)


@router.post("/{ordner:path}/anwenden/{n}", response_model=AnwendenAntwort)
async def anwenden(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                    settings: Settings = Depends(get_settings)):
    projekt_root = projekt_pfad(settings, ordner)
    projekt = projekt_root / "projekt"
    text_alt = pd.lies(pd.kapitel_datei(projekt, n))
    befunde = pd.lies(pd.befunde_datei(projekt, n))

    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        text_neu, _ = await _sammle_stream(
            base_url, "anachronismen_korrektur", pd.persona_lesen(projekt_root, "anachronismen_korrektur"),
            f"=== BEFUNDE (nur der Abschnitt Anachronismen ist relevant) ===\n{befunde}\n\n"
            f"=== KAPITELTEXT ===\n{text_alt}",
        )

    if woerter(text_neu) < woerter(text_alt) * KUERZUNGS_SCHWELLE:
        return AnwendenAntwort(alt=text_alt, neu=text_neu, gesichert_als=None)

    _, gesichert_als = pd.schreib(pd.kapitel_datei(projekt, n), text_neu)
    return AnwendenAntwort(alt=text_alt, neu=text_neu, gesichert_als=gesichert_als)


@router.post("/{ordner:path}/lektorieren/{n}", response_model=AnwendenAntwort)
async def lektorieren(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                       settings: Settings = Depends(get_settings)):
    projekt_root = projekt_pfad(settings, ordner)
    projekt = projekt_root / "projekt"
    text_alt = pd.lies(pd.kapitel_datei(projekt, n))
    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="(kein Geruest gefunden)")

    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        text_neu, _ = await _sammle_stream(
            base_url, "lektor", pd.persona_lesen(projekt_root, "lektor"),
            f"=== STORY-GERUEST (fuer Namen, Staende, Tonlage) ===\n{geruest_text}\n\n"
            f"=== KAPITELTEXT ===\n{text_alt}",
        )

    if woerter(text_neu) < woerter(text_alt) * KUERZUNGS_SCHWELLE:
        return AnwendenAntwort(alt=text_alt, neu=text_neu, gesichert_als=None)

    _, gesichert_als = pd.schreib(pd.kapitel_datei(projekt, n), text_neu)
    return AnwendenAntwort(alt=text_alt, neu=text_neu, gesichert_als=gesichert_als)


@router.post("/{ordner:path}/stand/{n}")
async def stand(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                 settings: Settings = Depends(get_settings)):
    projekt_root = projekt_pfad(settings, ordner)
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        text, auto_export = await _stand_ausfuehren(projekt_root, base_url, n)
    return {"stand": text, "auto_export": auto_export}


@router.post("/{ordner:path}/export")
def export(ordner: str, settings: Settings = Depends(get_settings)):
    projekt_root = projekt_pfad(settings, ordner)
    ganz = _export_ausfuehren(projekt_root / "projekt")
    # projekt_root.name statt hartcodiert "gesamt" - traegt (nach dem Fix
    # der Ordner-Umbenennung) den eigentlichen Geschichtennamen, siehe
    # app/core/projekt_dateien.py:projektordner_umbenennen.
    return {"gesamt": ganz, "dateiname": f"{projekt_root.name}.md"}


@router.get("/{ordner:path}/export/pdf")
def export_pdf(ordner: str, settings: Settings = Depends(get_settings)):
    projekt_root = projekt_pfad(settings, ordner)
    projekt = projekt_root / "projekt"
    kapitel_dateien = pd.vorhandene_kapitel(projekt)
    if not kapitel_dateien:
        raise HTTPException(404, "Keine Kapitel gefunden.")
    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
    epoche = pd.epoche_von_projekt(projekt_root)
    kapitel = [(pd.kapitelnummer_aus_dateiname(p), pd.lies(p)) for p in kapitel_dateien]
    pdf_bytes = buch_pdf_erzeugen(geruest_text, epoche, kapitel)
    # ordner kann bei aktivierten Epoche-Unterordnern einen "/" enthalten
    # (z.B. "Mittelalter/Im-Feuer-gestaehlt") - als Dateiname nur den
    # eigentlichen Projektnamen verwenden, kein "/" im Dateinamen.
    dateiname = projekt_root.name
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}.pdf"'},
    )


@router.post("/{ordner:path}/zusammenfassen")
def zusammenfassen(ordner: str, von: int | None = None, bis: int | None = None,
                    settings: Settings = Depends(get_settings)):
    projekt_root = projekt_pfad(settings, ordner)
    projekt = projekt_root / "projekt"
    if von is None or bis is None:
        return {"gesamt": _export_ausfuehren(projekt), "dateiname": f"{projekt_root.name}.md"}
    if von > bis:
        von, bis = bis, von
    alle = pd.vorhandene_kapitel(projekt)
    ausgewaehlt = [p for p in alle if von <= pd.kapitelnummer_aus_dateiname(p) <= bis]
    if not ausgewaehlt:
        raise HTTPException(404, f"Keine Kapitel im Bereich {von}-{bis} gefunden.")
    ganz = "\n\n".join(pd.lies(p) for p in ausgewaehlt)
    # Geschichtenname + Kapitelnummern als Suffix (z.B. "Die-Reise_2_3.md")
    # statt generischem "zusammen_02-03.md" - so bleibt auch bei mehreren
    # Zwischenstaenden erkennbar, zu welcher Geschichte und welchem
    # Kapitelbereich die Datei gehoert.
    ziel_name = f"{projekt_root.name}_{von}_{bis}.md"
    pd.schreib(projekt / ziel_name, ganz, force=True)
    return {"datei": ziel_name, "inhalt": ganz}


@router.get("/{ordner:path}/rechtschreibung/{n}", response_model=RechtschreibAntwort)
def rechtschreibung(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                     settings: Settings = Depends(get_settings)):
    projekt = projekt_pfad(settings, ordner) / "projekt"
    text = pd.lies(pd.kapitel_datei(projekt, n))
    unbekannt = h.hunspell_unbekannte_woerter(text, exec_fn=_hunspell_exec_fn(settings, ssh_ziel_id))
    if unbekannt is None:
        return RechtschreibAntwort(unbekannte_woerter=[], hunspell_verfuegbar=False)
    woerter_mit_satz = [
        RechtschreibWort(wort=w, satz=h.satz_mit_wort_finden(text, w)) for w in unbekannt
    ]
    return RechtschreibAntwort(unbekannte_woerter=woerter_mit_satz, hunspell_verfuegbar=True)
