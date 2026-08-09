"""HTTP-Anbindung an sd-server (stable-diffusion.cpp) fuer die
Deckblattbild-Generierung (siehe ToDo.md).

Analog zu app/core/ollama_client.py: base_url zeigt entweder auf ein lokales
sd-server oder auf das lokale Ende eines SSH-Tunnels (siehe
app/core/ssh_manager.py) - dieser Client weiss nichts von SSH. sd-server wird
mit fest verdrahteten Turbo-Generierungsparametern gestartet (Steps, CFG,
Sampler, Aufloesung - siehe Athene-Docker-Setup), deshalb schickt der Client
hier bewusst KEINE Sampling-Parameter (steps/cfg/sampler bleiben serverseitig
fix). Der Negative-Prompt ist davon unabhaengig - inhaltliche Gegensteuerung
gegen typische SD-Artefakte, siehe NEGATIV_PROMPT_STANDARD.
"""
from __future__ import annotations

import base64
import json

import httpx

# sd-servers OpenAI-kompatibler Endpunkt kennt kein eigenes JSON-Feld fuer
# negative_prompt (siehe routes_openai.cpp im stable-diffusion.cpp-Repo -
# geparst werden nur "prompt", "n", "size", "output_format",
# "output_compression"). Zusaetzliche SDGenerationParams-Felder wie
# negative_prompt werden stattdessen ueber ein in den Prompt-Text
# eingebettetes "<sd_cpp_extra_args>{...}</sd_cpp_extra_args>"-JSON
# durchgereicht (per Regex aus dem Prompt herausgeloest, siehe
# common.cpp:extract_and_remove_sd_cpp_extra_args/SDGenerationParams::
# from_json_str - "negative_prompt" ist dort ein direkt geladenes Feld).
#
# Ohne Gegensteuerung neigt gerade das hier laufende Turbo/Distill-Modell
# (wenige Sampling-Schritte, siehe Modul-Kommentar oben) zu Anatomie-
# Artefakten wie Extra-Gliedmassen - eine rein positive Prompt-Formulierung
# wie "strictly one pair of arms" hilft kaum, weil Diffusionsmodelle
# Negationen im Prompt nicht zuverlaessig verstehen. Bewusst als fester,
# immer mitgeschickter Standard-Satz statt als vom User editierbares Feld:
# die Artefaktklasse ist modellbedingt, nicht geschichtenspezifisch.
NEGATIV_PROMPT_STANDARD = (
    "extra limbs, extra arms, extra hands, extra legs, extra fingers, "
    "fused fingers, missing fingers, deformed hands, mutated hands, "
    "malformed limbs, disfigured, duplicate body parts, bad anatomy, "
    "blurry, low quality, watermark, text"
)


class BildGenerierungFehler(Exception):
    pass


def _prompt_mit_extra_args(prompt: str, negativ_prompt: str) -> str:
    """Haengt negativ_prompt als eingebettetes sd_cpp_extra_args-JSON an den
    Prompt an (siehe Modul-Kommentar zu NEGATIV_PROMPT_STANDARD) - json.dumps
    statt manuellem String-Bau, damit Anfuehrungszeichen im Prompt/Negativ-
    Prompt korrekt escaped werden."""
    extra_args = json.dumps({"negative_prompt": negativ_prompt}, ensure_ascii=False)
    return f"{prompt}\n<sd_cpp_extra_args>{extra_args}</sd_cpp_extra_args>"


async def generiere_cover(base_url: str, prompt: str, timeout: float = 120.0,
                           negativ_prompt: str = NEGATIV_PROMPT_STANDARD) -> bytes:
    """Ruft sd-servers OpenAI-kompatiblen Endpunkt auf (siehe
    examples/server/routes_openai.cpp im stable-diffusion.cpp-Repo) und
    liefert die rohen PNG-Bytes des ersten (einzigen) Ergebnisbilds.
    negativ_prompt wird als sd_cpp_extra_args in den Prompt eingebettet
    (siehe _prompt_mit_extra_args) - leer lassen, um ganz ohne Negative-
    Prompt zu generieren."""
    gesamt_prompt = _prompt_mit_extra_args(prompt, negativ_prompt) if negativ_prompt else prompt
    payload = {"prompt": gesamt_prompt}
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
