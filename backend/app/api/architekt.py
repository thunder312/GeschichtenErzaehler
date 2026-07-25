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

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.auth import get_current_user, get_current_user_ws
from app.config import Settings, get_settings
from app.core import architekt as arch
from app.core import projekt_dateien as pd
from app.core.ollama_client import OllamaFehler, chat_stream
from app.schemas import Benutzer
from app.services import ollama_basis_url, ordner_nach_umbenennung, projekt_pfad

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


async def _zug(websocket: WebSocket, base_url: str, persona_text: str,
                verlauf: list[str], eingabe: str) -> tuple[str, bool]:
    verlauf.append(f"Ich: {eingabe}")
    await websocket.send_json({"phase": "frage", "typ": "start"})

    teile: list[str] = []
    async for event in chat_stream(base_url, "architekt", persona_text, arch.verlauf_zu_text(verlauf)):
        if event.typ == "error":
            await websocket.send_json({"phase": "fehler", "typ": "error", "text": event.text})
            raise OllamaFehler(event.text)
        if event.typ == "thinking":
            await websocket.send_json({"phase": "frage", "typ": "denkt_nach"})
        if event.typ == "content":
            teile.append(event.text)

    antwort = "".join(teile).strip()
    ist_geruest = arch.ist_geruest_antwort(antwort)
    if not ist_geruest:
        antwort = arch.nur_erste_frage(antwort)
    verlauf.append(f"Du: {antwort}")
    return antwort, ist_geruest


@router.websocket("/{ordner:path}/ws/architekt")
async def ws_architekt(websocket: WebSocket, ordner: str, ssh_ziel_id: str | None = None,
                        benutzer: Benutzer = Depends(get_current_user_ws)):
    settings = get_settings()
    await websocket.accept()
    try:
        projekt_root = projekt_pfad(settings, benutzer.username, ordner)
        persona_text = pd.persona_lesen(projekt_root, "architekt")

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
                antwort, fertig = await _zug(websocket, base_url, persona_text, verlauf, ERSTE_EINGABE)
                _verlauf_speichern(projekt_root, verlauf)

            while True:
                if fertig:
                    _, gesichert_als = pd.schreib(pd.geruest_datei(projekt_root / "projekt"), antwort, force=True)
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
                    })
                    break

                await websocket.send_json({"phase": "frage", "typ": "fertig", "text": antwort})

                nachricht = await websocket.receive_json()
                eingabe = (nachricht.get("eingabe") or "").strip()
                if not eingabe or eingabe.lower() in ("ende", "exit", "quit"):
                    _verlauf_loeschen(projekt_root)
                    await websocket.send_json({"phase": "beendet_ohne_speichern"})
                    break

                antwort, fertig = await _zug(websocket, base_url, persona_text, verlauf, eingabe)
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
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
