"""HTTP-Anbindung an sd-server (stable-diffusion.cpp) fuer die
Deckblattbild-Generierung (siehe ToDo.md).

Analog zu app/core/ollama_client.py: base_url zeigt entweder auf ein lokales
sd-server oder auf das lokale Ende eines SSH-Tunnels (siehe
app/core/ssh_manager.py) - dieser Client weiss nichts von SSH. sd-server wird
mit fest verdrahteten Turbo-Generierungsparametern gestartet (Steps, CFG,
Sampler, Aufloesung - siehe Athene-Docker-Setup), deshalb schickt der Client
hier bewusst nur den Prompt, keine Sampling-Parameter.
"""
from __future__ import annotations

import base64

import httpx


class BildGenerierungFehler(Exception):
    pass


async def generiere_cover(base_url: str, prompt: str, timeout: float = 120.0) -> bytes:
    """Ruft sd-servers OpenAI-kompatiblen Endpunkt auf (siehe
    examples/server/routes_openai.cpp im stable-diffusion.cpp-Repo) und
    liefert die rohen PNG-Bytes des ersten (einzigen) Ergebnisbilds."""
    payload = {"prompt": prompt}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            antwort = await client.post(f"{base_url}/v1/images/generations", json=payload)
            if antwort.status_code >= 400:
                raise BildGenerierungFehler(
                    f"sd-server antwortet mit HTTP {antwort.status_code}: "
                    f"{antwort.text[:500]}"
                )
            daten = antwort.json()
    except httpx.HTTPError as e:
        raise BildGenerierungFehler(
            f"sd-server nicht erreichbar unter {base_url}: {e}. Laeuft der "
            f"Container? Bei einem entfernten Ziel: SSH-Verbindung/Tunnel "
            f"pruefen."
        ) from e

    bilder = daten.get("data", [])
    if not bilder or not bilder[0].get("b64_json"):
        raise BildGenerierungFehler("sd-server hat kein Bild geliefert.")
    try:
        return base64.b64decode(bilder[0]["b64_json"])
    except (ValueError, TypeError) as e:
        raise BildGenerierungFehler(f"Bilddaten von sd-server nicht dekodierbar: {e}") from e
