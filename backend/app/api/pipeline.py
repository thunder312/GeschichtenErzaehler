"""Die eigentlichen Pipeline-Schritte: Schreiben (WebSocket, streamend),
Pruefen (Anachronismus/Stimmigkeit, Kontinuitaet UND Lektorat laufen
parallel und liefern eine gemeinsame Fund-Liste, siehe _pruefe_kapitel),
Stand, Export/Zusammenfassen, Rechtschreibpruefung.

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

import asyncio
import functools
import hashlib
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.auth import get_current_user, get_current_user_ws
from app.config import Settings, get_settings
from app.core import geruest as g
from app.core import heuristik as h
from app.core import projekt_dateien as pd
from app.core import ssh_manager
from app.core.befunde_merge import RoherBefund, befunde_zusammenfuehren
from app.core.fundstellen import finde_fundstelle
from app.core.ollama_client import OllamaFehler, chat_stream
from app.core.pdf_export import buch_pdf_erzeugen
from app.core.pruef_schema import AnachronismusAntwortLLM, KontinuitaetAntwortLLM, LektorAntwortLLM
from app.core.rollen import ROLLEN, STUFE_DIREKTIVEN
from app.core.textutil import woerter
from app.schemas import Befund, BefundeAntwort, Benutzer, RechtschreibAntwort, RechtschreibWort
from app.services import ollama_basis_url, projekt_pfad, ssh_ziel_aus_db

router = APIRouter(prefix="/api/projects", tags=["pipeline"])

# Unter dieser Schwelle (Anteil der Zielwortzahl) wird bei eingeschalteter
# automatischer Fortsetzung weitergeschrieben, bzw. ohne Fortsetzung nur
# gewarnt (siehe Bedienungsanleitung Abschnitt 9b).
FORTSETZEN_SCHWELLE = 0.70
FORTSETZEN_MAX_VERSUCHE = 3


async def _sammle_stream(
    base_url: str, rolle: str, system: str, user: str, format: dict | str | None = None,
) -> tuple[str, dict]:
    text = ""
    meta: dict = {}
    async for event in chat_stream(base_url, rolle, system, user, format=format):
        if event.typ == "error":
            raise HTTPException(502, f"Ollama-Fehler ({rolle}): {event.text}")
        if event.typ == "done":
            text, meta = event.text, event.meta
    if not text:
        raise HTTPException(502, f"Leere Antwort von Rolle '{rolle}' erhalten.")
    return text, meta


def _anachronismus_roh_befunde(kapiteltext: str, antwort_text: str) -> list[RoherBefund]:
    try:
        antwort = AnachronismusAntwortLLM.model_validate_json(antwort_text)
    except ValidationError:
        return [RoherBefund(
            kategorie="anachronismus", fundstelle="", sicherheit="gering", vorschlag=None,
            beschreibung="Antwort des Anachronismus-/Stimmigkeits-Pruefers konnte nicht gelesen werden (kein gueltiges JSON).",
            start=None, end=None,
        )]
    ergebnis = []
    for eintrag in antwort.befunde:
        bereich = finde_fundstelle(kapiteltext, eintrag.fundstelle)
        ergebnis.append(RoherBefund(
            kategorie=eintrag.kategorie,
            fundstelle=eintrag.fundstelle,
            beschreibung=eintrag.problem,
            sicherheit=eintrag.sicherheit,
            vorschlag=eintrag.vorschlag,
            start=bereich[0] if bereich else None,
            end=bereich[1] if bereich else None,
        ))
    return ergebnis


def _kontinuitaet_roh_befunde(kapiteltext: str, antwort_text: str) -> list[RoherBefund]:
    try:
        antwort = KontinuitaetAntwortLLM.model_validate_json(antwort_text)
    except ValidationError:
        return [RoherBefund(
            kategorie="kontinuitaet", fundstelle="", sicherheit=None, vorschlag=None,
            beschreibung="Antwort des Kontinuitaets-Pruefers konnte nicht gelesen werden (kein gueltiges JSON).",
            start=None, end=None,
        )]
    ergebnis = []
    for eintrag in antwort.befunde:
        bereich = finde_fundstelle(kapiteltext, eintrag.zitat)
        beschreibung = eintrag.widerspruch
        if eintrag.beleg:
            beschreibung += f" (Beleg: {eintrag.beleg})"
        ergebnis.append(RoherBefund(
            kategorie="kontinuitaet",
            fundstelle=eintrag.zitat,
            beschreibung=beschreibung,
            sicherheit=None,
            vorschlag=None if eintrag.unsicher else eintrag.vorschlag,
            start=bereich[0] if bereich else None,
            end=bereich[1] if bereich else None,
        ))
    return ergebnis


def _lektor_roh_befunde(kapiteltext: str, antwort_text: str) -> list[RoherBefund]:
    try:
        antwort = LektorAntwortLLM.model_validate_json(antwort_text)
    except ValidationError:
        return [RoherBefund(
            kategorie="lektorat", fundstelle="", sicherheit="hoch", vorschlag=None,
            beschreibung="Antwort des Lektors konnte nicht gelesen werden (kein gueltiges JSON).",
            start=None, end=None,
        )]
    ergebnis = []
    for eintrag in antwort.befunde:
        bereich = finde_fundstelle(kapiteltext, eintrag.fundstelle)
        ergebnis.append(RoherBefund(
            kategorie="lektorat",
            fundstelle=eintrag.fundstelle,
            beschreibung=eintrag.problem,
            # Lektor meldet laut Persona nur, was er auch sicher als echten
            # Duden-Verstoss erkennt (kein Sicherheits-Feld im Modell noetig,
            # anders als bei Anachronismus/Stimmigkeit) - daher konstant
            # "hoch", damit die Merge-Logik es wie die anderen "hoch"-Funde
            # behandelt.
            sicherheit="hoch",
            vorschlag=eintrag.vorschlag,
            start=bereich[0] if bereich else None,
            end=bereich[1] if bereich else None,
        ))
    return ergebnis


async def _bei_bedarf_fortsetzen(
    websocket: WebSocket, base_url: str, projekt_root: Path, n: int, text: str,
    ziel: int, geruest_text: str, vorher: str, stufe: str, zusatzhinweis: str,
    autor_rolle: str,
) -> tuple[str, list[h.Finding]]:
    """Lässt den Autor nahtlos weiterschreiben, wenn ein Kapitel deutlich zu
    kurz ausfällt - portiert aus pre-GUI/novelle.py:_bei_bedarf_fortsetzen
    (siehe Bedienungsanleitung Abschnitt 9b), inklusive WebSocket-Streaming
    der Fortsetzung analog zum ersten Entwurf in ws_schreiben. Nur aktiv,
    wenn 'Automatische Fortsetzung: Ein' im Geruest steht."""
    findings: list[h.Finding] = []
    versuch = 0
    aktueller_block = g.kapitel_block_erkennen(geruest_text, n)
    aktueller_hinweis = (
        f"\n\n=== NUR DIESES KAPITEL FORTSETZEN (Kapitel {n}) ===\n{aktueller_block}\n\n"
        f"Bleibe ausschließlich in der oben für DIESES Kapitel beschriebenen "
        f"Stufe der Liebeshandlung. Erfinde KEINE neue Szene und springe zu "
        f"KEINEM anderen Beziehungsstand (z.B. Heirat, körperliche Vereinigung "
        f"oder ein gemeinsames Erwachen als Paar), auch wenn ein späteres "
        f"Kapitel im Gesamtplan das vorsieht - das gehört nicht hierher. "
        f"Führe exakt die laufende Szene fort."
        if aktueller_block else ""
    )
    zusatz_block = (
        f"\n\n=== ZUSÄTZLICHER HINWEIS FÜR DIESEN VERSUCH ===\n{zusatzhinweis}\n"
        f"Dieser Hinweis gilt nur für diesen einen Schreibversuch und hat "
        f"Vorrang, falls er einem Detail des Geruests widerspricht."
        if zusatzhinweis else ""
    )

    while woerter(text) < ziel * FORTSETZEN_SCHWELLE and versuch < FORTSETZEN_MAX_VERSUCHE:
        versuch += 1
        fehlend = ziel - woerter(text)
        # Nur das Ende als Anschlusspunkt mitgeben, nicht den ganzen Text
        # erneut - spart Kontext und verhindert, dass der Autor von vorn
        # beginnt.
        anschluss = text[-600:]

        await websocket.send_json({
            "phase": "autor_fortsetzung", "typ": "start",
            "versuch": versuch, "max_versuche": FORTSETZEN_MAX_VERSUCHE,
            "woerter": woerter(text), "ziel_woerter": ziel,
        })

        teile: list[str] = []
        async for event in chat_stream(
            base_url, autor_rolle, pd.persona_lesen(projekt_root, "autor"),
            f"=== STORY-GERUEST ===\n{geruest_text}\n\n"
            f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
            f"=== BISHERIGER TEXT DIESES KAPITELS (Ende) ===\n...{anschluss}\n\n"
            f"=== AUFTRAG ===\n"
            f"Der obige Text ist noch nicht zu Ende. Schreibe NAHTLOS weiter, "
            f"genau ab der letzten Zeile, ohne sie zu wiederholen und ohne "
            f"neu zu beginnen. Führe die Szene tatsächlich aus, statt sie "
            f"nur anzudeuten oder abzukürzen. Noch etwa {fehlend} Wörter, "
            f"bis das Kapitel gemäß Geruest inhaltlich abgeschlossen ist. "
            f"Gib ausschließlich die Fortsetzung aus, keine Wiederholung "
            f"des bisherigen Textes. Schreibe ausschließlich auf Deutsch, "
            f"auch wenn im bisherigen Text ein anderer Sprachanteil "
            f"vorkommen sollte.\n\n"
            f"{STUFE_DIREKTIVEN[stufe]}{aktueller_hinweis}{zusatz_block}",
        ):
            if event.typ == "error":
                raise OllamaFehler(event.text)
            if event.typ in ("thinking", "content"):
                if event.typ == "content":
                    teile.append(event.text)
                await websocket.send_json({"phase": "autor_fortsetzung", "typ": event.typ, "text": event.text})
            if event.typ == "done":
                await websocket.send_json({"phase": "autor_fortsetzung", "typ": "done", "versuch": versuch})

        fortsetzung = h.meta_zeilen_entfernen("".join(teile).strip())
        fortsetzung, dup_findings = h.fuehrende_duplikate_entfernen(text, fortsetzung)
        findings += dup_findings
        text = text.rstrip() + "\n\n" + fortsetzung.strip()
        text, findings_neustart = h.kapitel_neustart_abschneiden(text)
        text, findings_ende = h.vorzeitige_kapitelende_abschneiden(text)
        findings += findings_neustart + findings_ende

    if woerter(text) < ziel * FORTSETZEN_SCHWELLE:
        findings.append(h.Finding(
            "zu_kurz",
            f"Auch nach {versuch} Fortsetzungsversuchen bleibt Kapitel {n} "
            f"kurz ({woerter(text)} von {ziel} Wörtern). Persona oder "
            f"Gerüststruktur prüfen, statt weiter automatisch zu versuchen.",
            schwere="info",
        ))

    return text, findings


async def _pruefe_kapitel(projekt: Path, base_url: str, n: int, kapiteltext: str) -> BefundeAntwort:
    geruest_text = pd.lies(pd.geruest_datei(projekt))
    verbote = pd.lies(pd.verbotsliste_datei(projekt), pflicht=False, ersatz="")
    vorher = pd.lies(pd.stand_datei(projekt, n - 1), pflicht=False,
                      ersatz="(Kein vorheriger Stand vorhanden. Dies ist das erste Kapitel.)")
    jahr = g.jahr_erkennen(geruest_text)

    # Alle drei Pruefer sind voneinander unabhaengig (unterschiedliche
    # Eingaben, kein gemeinsamer Zustand) - parallel starten statt
    # nacheinander, um die Wartezeit pro Kapitel zu verkuerzen. "format=json"
    # erzwingt eine strukturierte Antwort, die deterministisch geparst werden
    # kann statt freiformuliertes Markdown/Fliesstext zu interpretieren.
    (anachronismen_text, _), (kontinuitaet_text, _), (lektor_text, _) = await asyncio.gather(
        _sammle_stream(
            base_url, "anachronismus", pd.persona_lesen(projekt.parent, "pruefer_anachronismus"),
            f"JAHR: {jahr}\n\n=== VERBOTSLISTE ===\n{verbote}\n\n=== KAPITELTEXT ===\n{kapiteltext}",
            format="json",
        ),
        _sammle_stream(
            base_url, "kontinuitaet", pd.persona_lesen(projekt.parent, "pruefer_kontinuitaet"),
            f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n=== NEUES KAPITEL {n} ===\n{kapiteltext}",
            format="json",
        ),
        _sammle_stream(
            base_url, "lektor", pd.persona_lesen(projekt.parent, "lektor"),
            f"=== STORY-GERUEST ===\n{geruest_text}\n\n=== KAPITELTEXT ===\n{kapiteltext}",
            format="json",
        ),
    )

    roh_befunde = (
        _anachronismus_roh_befunde(kapiteltext, anachronismen_text)
        + _kontinuitaet_roh_befunde(kapiteltext, kontinuitaet_text)
        + _lektor_roh_befunde(kapiteltext, lektor_text)
    )
    befunde = [Befund(**b) for b in befunde_zusammenfuehren(kapiteltext, roh_befunde)]

    antwort = BefundeAntwort(
        kapitel=n, erzeugt_am=time.strftime("%Y-%m-%d %H:%M"), jahr=jahr, befunde=befunde,
        quelltext_sha256=hashlib.sha256(kapiteltext.encode("utf-8")).hexdigest(),
    )
    pd.schreib(pd.befunde_datei(projekt, n), antwort.model_dump_json(indent=2))
    return antwort


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
        _export_ausfuehren(projekt_root)
    return text, auto_export


def _export_ausfuehren(projekt_root: Path) -> str:
    """Schreibt die Gesamtdatei in den Story-Root (NICHT in den projekt/-
    Arbeitsdateien-Unterordner) - dort sollen nur Arbeitsdateien liegen,
    Exporte/Endergebnisse eine Ebene hoeher, siehe ToDo.md Deployment.
    Dateiname folgt dem aktuellen Projekttitel (= Ordnername), nicht mehr
    hartcodiert "gesamt.md"."""
    projekt = projekt_root / "projekt"
    kapitel = pd.vorhandene_kapitel(projekt)
    if not kapitel:
        raise HTTPException(404, "Keine Kapitel gefunden.")
    ganz = "\n\n".join(pd.lies(p) for p in kapitel)
    ziel = projekt_root / f"{projekt_root.name}.md"
    pd.schreib(ziel, ganz, force=True)
    # Altlast aus einer frueheren Version (fester Dateiname "gesamt.md")
    # aufraeumen, damit nicht zwei widerspruechliche Exporte nebeneinander
    # liegen bleiben.
    alte_datei = projekt_root / "gesamt.md"
    if alte_datei != ziel and alte_datei.exists():
        alte_datei.unlink()
    return ganz


@router.websocket("/{ordner:path}/ws/schreiben/{n}")
async def ws_schreiben(websocket: WebSocket, ordner: str, n: int,
                        zusatzhinweis: str = "", ssh_ziel_id: str | None = None,
                        benutzer: Benutzer = Depends(get_current_user_ws)):
    settings = get_settings()
    await websocket.accept()
    try:
        projekt_root = projekt_pfad(settings, benutzer.username, ordner)
        projekt = projekt_root / "projekt"

        # Stand-Sicherstellung (siehe Schnittstellen-Uebersicht 5.14): fehlt
        # stand_(n-1).md, aber Kapitel n-1 existiert, wird er zuerst nachgeholt.
        if n > 1 and not pd.stand_datei(projekt, n - 1).exists():
            if not pd.kapitel_datei(projekt, n - 1).exists():
                await websocket.send_json({
                    "phase": "fehler", "typ": "error",
                    "text": f"Weder stand_{n-1:02d}.md noch kapitel_{n-1:02d}.md "
                            f"vorhanden - Kapitel müssen der Reihe nach geschrieben werden.",
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

            zielsatz = f"Zielumfang: etwa {ziel} Wörter." if ziel else ""
            aktueller_hinweis = (
                f"\n\n=== NUR DIESES KAPITEL SCHREIBEN (Kapitel {n}) ===\n{kapitel_block}\n\n"
                f"Bleibe ausschließlich in der oben für DIESES Kapitel beschriebenen "
                f"Stufe der Liebeshandlung. Verwende KEINE Ereignisse, keine Explizitheit "
                f"und keinen Beziehungsstand aus einem ANDEREN Kapitel des Gesamtplans."
                if kapitel_block else ""
            )
            zusatz_block = (
                f"\n\n=== ZUSÄTZLICHER HINWEIS FÜR DIESEN VERSUCH ===\n{zusatzhinweis}\n"
                f"Dieser Hinweis gilt nur für diesen einen Schreibversuch und hat "
                f"Vorrang, falls er einem Detail des Geruests widerspricht."
                if zusatzhinweis else ""
            )
            user_prompt = (
                f"=== STORY-GERUEST ===\n{geruest_text}\n\n"
                f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
                f"=== AUFTRAG ===\nSchreibe Kapitel {n}. {zielsatz}\n"
                f"Gib ausschließlich den Kapiteltext aus.\n\n"
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

            if ziel and g.automatische_fortsetzung_aktiviert(geruest_text):
                text, findings_fortsetzung = await _bei_bedarf_fortsetzen(
                    websocket, base_url, projekt_root, n, text, ziel,
                    geruest_text, vorher, stufe, zusatzhinweis, autor_rolle,
                )
                findings += findings_fortsetzung
            elif ziel and woerter(text) < ziel * FORTSETZEN_SCHWELLE:
                findings.append(h.Finding(
                    "zu_kurz",
                    f"Kapitel {n} liegt bei {woerter(text)} von {ziel} Wörtern "
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
                        f"Umfang weicht deutlich ab: {ist} statt {ziel} Wörter ({abw:+.0f} %).",
                    ))

            findings += h.alle_nachbearbeitungs_checks(text, geruest_text, stufe)

            unbekannt = h.hunspell_unbekannte_woerter(
                text, exec_fn=_hunspell_exec_fn(settings, ssh_ziel_id),
            )
            if unbekannt:
                findings.append(h.Finding(
                    "rechtschreibung",
                    f"hunspell kennt folgende Wörter nicht (Eigennamen, "
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
            befunde_antwort = await _pruefe_kapitel(projekt, base_url, n, text)
            await websocket.send_json({"phase": "pruefen", "typ": "done", "befunde": befunde_antwort.model_dump()})

            await websocket.send_json({"phase": "abgeschlossen", "kapitel_text": text})

    except OllamaFehler as e:
        await websocket.send_json({"phase": "fehler", "typ": "error", "text": str(e)})
    except HTTPException as e:
        await websocket.send_json({"phase": "fehler", "typ": "error", "text": e.detail})
    except WebSocketDisconnect:
        return
    except Exception as e:
        # Sicherheitsnetz gegen unerwartete Fehler (z.B. ein zukuenftiger Bug
        # wie der SSHVerbindungsFehler-Absturz durch hunspell auf einem
        # "direct"-KI-Ziel): lieber eine Fehlermeldung ans Frontend schicken,
        # als dass FastAPI versucht, auf die schon offene WebSocket-
        # Verbindung noch eine HTTP-Fehlerantwort zu schreiben (kracht mit
        # "Unexpected ASGI message" und reisst die Verbindung ohne jede
        # Frontend-Nachricht ab).
        await websocket.send_json({"phase": "fehler", "typ": "error", "text": str(e)})
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


def _hunspell_exec_fn(settings: Settings, ssh_ziel_id: str | None):
    if not ssh_ziel_id:
        return None
    ziel = ssh_ziel_aus_db(settings, ssh_ziel_id)
    if ziel.auth_method == "direct":
        # "Direkt"-Ziele haben nur eine HTTP-Basis-URL fuer Ollama, keine
        # echte SSH-Verbindung - exec_command (fuer hunspell) kann hier
        # nicht laufen. Ohne diese Abfrage versuchte ssh_manager._connect()
        # buchstaeblich "http://127.0.0.1:18321" als SSH-Hostnamen aufzuloesen
        # und krachte mit einer nicht abgefangenen SSHVerbindungsFehler mitten
        # im WebSocket-Handler (siehe ws_schreiben) - das Kapitel war zu dem
        # Zeitpunkt zwar schon gespeichert, aber die "abgeschlossen"-Nachricht
        # kam nie beim Frontend an.
        return None
    return functools.partial(ssh_manager.exec_command, ziel)


@router.post("/{ordner:path}/pruefen/{n}", response_model=BefundeAntwort)
async def pruefen(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                   settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    kapiteltext = pd.lies(pd.kapitel_datei(projekt, n))
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        return await _pruefe_kapitel(projekt, base_url, n, kapiteltext)


@router.post("/{ordner:path}/stand/{n}")
async def stand(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                 settings: Settings = Depends(get_settings),
                 benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    with ollama_basis_url(settings, ssh_ziel_id) as base_url:
        text, auto_export = await _stand_ausfuehren(projekt_root, base_url, n)
    return {"stand": text, "auto_export": auto_export}


@router.post("/{ordner:path}/export")
def export(ordner: str, settings: Settings = Depends(get_settings),
           benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    ganz = _export_ausfuehren(projekt_root)
    # projekt_root.name statt hartcodiert "gesamt" - traegt (nach dem Fix
    # der Ordner-Umbenennung) den eigentlichen Geschichtennamen, siehe
    # app/core/projekt_dateien.py:projektordner_umbenennen.
    return {"gesamt": ganz, "dateiname": f"{projekt_root.name}.md"}


@router.get("/{ordner:path}/export/pdf")
def export_pdf(ordner: str, settings: Settings = Depends(get_settings),
                benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
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
                    settings: Settings = Depends(get_settings),
                    benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    projekt = projekt_root / "projekt"
    if von is None or bis is None:
        return {"gesamt": _export_ausfuehren(projekt_root), "dateiname": f"{projekt_root.name}.md"}
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
    # Kapitelbereich die Datei gehoert. Landet im Story-Root, nicht im
    # projekt/-Arbeitsdateien-Unterordner (siehe _export_ausfuehren).
    ziel_name = f"{projekt_root.name}_{von}_{bis}.md"
    pd.schreib(projekt_root / ziel_name, ganz, force=True)
    return {"datei": ziel_name, "inhalt": ganz}


@router.get("/{ordner:path}/rechtschreibung/{n}", response_model=RechtschreibAntwort)
def rechtschreibung(ordner: str, n: int, ssh_ziel_id: str | None = Query(None),
                     settings: Settings = Depends(get_settings),
                     benutzer: Benutzer = Depends(get_current_user)):
    projekt = projekt_pfad(settings, benutzer.username, ordner) / "projekt"
    text = pd.lies(pd.kapitel_datei(projekt, n))
    unbekannt = h.hunspell_unbekannte_woerter(text, exec_fn=_hunspell_exec_fn(settings, ssh_ziel_id))
    if unbekannt is None:
        return RechtschreibAntwort(unbekannte_woerter=[], hunspell_verfuegbar=False)
    woerter_mit_satz = [
        RechtschreibWort(wort=w, satz=h.satz_mit_wort_finden(text, w)) for w in unbekannt
    ]
    return RechtschreibAntwort(unbekannte_woerter=woerter_mit_satz, hunspell_verfuegbar=True)
