"""Ollama-HTTP-Anbindung - async Neuimplementierung von novelle.py's
ollama_chat()/ollama_get() (siehe doc/Schnittstellen-Uebersicht.md
Abschnitt 3).

Bewusster Unterschied zum Original: statt synchron auf stderr zu streamen,
liefert chat_stream() ein asyncio-Generator von ChatEvent-Objekten, die die
FastAPI-Route 1:1 in eine WebSocket-Verbindung weiterreicht (siehe
app/api/pipeline.py). base_url zeigt entweder auf ein lokales Ollama oder
auf das lokale Ende eines SSH-Tunnels (siehe app/core/ssh_manager.py) - der
Client selbst weiss nichts von SSH, er spricht immer nur HTTP gegen
base_url.
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

from app.core.rollen import KEEP_ALIVE, ROLLEN
from app.core.textutil import woerter


class OllamaFehler(Exception):
    pass


@dataclass
class ChatEvent:
    typ: str  # "thinking" | "content" | "done" | "error"
    text: str = ""
    meta: dict = field(default_factory=dict)


async def chat_stream(
    base_url: str,
    rolle: str,
    system: str,
    user: str,
    ueberschreibe: dict | None = None,
    timeout: float = 3600.0,
) -> AsyncIterator[ChatEvent]:
    if rolle not in ROLLEN:
        raise OllamaFehler(f"Unbekannte Rolle: {rolle}")

    cfg = ROLLEN[rolle]
    optionen = dict(cfg["optionen"])
    if ueberschreibe:
        optionen.update(ueberschreibe)

    payload = {
        "model": cfg["modell"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "think": cfg.get("think", False),
        "options": optionen,
    }

    start = time.time()
    teile: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{base_url}/api/chat", json=payload,
            ) as antwort:
                if antwort.status_code >= 400:
                    body = await antwort.aread()
                    raise OllamaFehler(
                        f"Ollama antwortet mit HTTP {antwort.status_code}: "
                        f"{body.decode(errors='replace')[:500]}"
                    )
                async for zeile in antwort.aiter_lines():
                    zeile = zeile.strip()
                    if not zeile:
                        continue
                    try:
                        stueck = json.loads(zeile)
                    except json.JSONDecodeError:
                        continue

                    if "error" in stueck:
                        yield ChatEvent("error", text=stueck["error"])
                        return

                    nachricht = stueck.get("message", {})
                    gedanke = nachricht.get("thinking")
                    if gedanke:
                        yield ChatEvent("thinking", text=gedanke)

                    inhalt = nachricht.get("content", "")
                    if inhalt:
                        teile.append(inhalt)
                        yield ChatEvent("content", text=inhalt)

                    if stueck.get("done"):
                        dauer = stueck.get("eval_duration", 0) / 1e9
                        anzahl = stueck.get("eval_count", 0)
                        rate = anzahl / dauer if dauer else 0
                        yield ChatEvent("done", text="".join(teile).strip(), meta={
                            "token": anzahl,
                            "sekunden": round(time.time() - start, 1),
                            "token_pro_sekunde": round(rate, 1),
                            "done_reason": stueck.get("done_reason", ""),
                            "woerter": woerter("".join(teile)),
                        })
                        return
    except httpx.HTTPError as e:
        raise OllamaFehler(
            f"Ollama nicht erreichbar unter {base_url}: {e}. Laeuft der "
            f"Container? Bei einem entfernten Ziel: SSH-Verbindung/Tunnel "
            f"pruefen."
        ) from e


async def ps(base_url: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{base_url}/api/ps")
        r.raise_for_status()
        return r.json()


async def tags(base_url: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{base_url}/api/tags")
        r.raise_for_status()
        return r.json()


def tags_sync(base_url: str, timeout: float = 10.0) -> dict:
    """Synchrone Variante fuer den Verbindungstest eines 'direct'-KI-Ziels
    (siehe app/api/ssh_targets.py) - die Test-Endpunkte sind bewusst
    synchron, analog zum blockierenden paramiko-Verbindungstest fuer
    SSH-Ziele."""
    with httpx.Client(timeout=timeout) as client:
        r = client.get(f"{base_url}/api/tags")
        r.raise_for_status()
        return r.json()
