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
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.core import architekt as arch
from app.core import projekt_dateien as pd
from app.core.ollama_client import OllamaFehler, chat_stream
from app.services import ollama_basis_url, projekt_pfad

router = APIRouter(prefix="/api/projects", tags=["architekt"])

ERSTE_EINGABE = "Lass uns anfangen. Stelle mir die ersten Fragen."


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


@router.websocket("/{ordner}/ws/architekt")
async def ws_architekt(websocket: WebSocket, ordner: str, ssh_ziel_id: str | None = None):
    settings = get_settings()
    await websocket.accept()
    try:
        projekt_root = projekt_pfad(settings, ordner)
        persona_text = pd.persona_lesen(projekt_root, "architekt")
        verlauf: list[str] = []

        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            antwort, fertig = await _zug(websocket, base_url, persona_text, verlauf, ERSTE_EINGABE)

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

                    neuer_ordner = pd.projektordner_umbenennen(projekt_root, antwort)

                    await websocket.send_json({
                        "phase": "abgeschlossen",
                        "geruest": antwort,
                        "ausgangslage_gespeichert": ausgangslage_gespeichert,
                        "gesichert_als": gesichert_als,
                        "neuer_ordner": neuer_ordner or ordner,
                    })
                    break

                await websocket.send_json({"phase": "frage", "typ": "fertig", "text": antwort})

                nachricht = await websocket.receive_json()
                eingabe = (nachricht.get("eingabe") or "").strip()
                if not eingabe or eingabe.lower() in ("ende", "exit", "quit"):
                    await websocket.send_json({"phase": "beendet_ohne_speichern"})
                    break

                antwort, fertig = await _zug(websocket, base_url, persona_text, verlauf, eingabe)

    except OllamaFehler:
        pass
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
