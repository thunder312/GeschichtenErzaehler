"""HTTP-Anbindung an sd-server (stable-diffusion.cpp) fuer die
Deckblattbild-Generierung (siehe ToDo.md).

Analog zu app/core/ollama_client.py: base_url zeigt entweder auf ein lokales
sd-server oder auf das lokale Ende eines SSH-Tunnels (siehe
app/core/ssh_manager.py) - dieser Client weiss nichts von SSH. sd-server
startet zwar mit Turbo-Standardwerten (Modell sd_xl_turbo_1.0, CFG 1.0,
1024x1024 - siehe Athene-Docker-Setup), diese sind aber KEIN serverseitiges
Hardlimit: per Live-Test gegen den echten Athene-Server (2026-08-09/10)
uebernimmt sd-server sample_steps/width/height aus sd_cpp_extra_args
tatsaechlich.

Wichtigster Befund aus diesen Tests: bei der Server-Standardaufloesung
1024x1024 trat unabhaengig von Steps (4 oder 8) und CFG (1.0 bis 4.0)
zuverlaessig "Subjekt-Verdopplung" auf (eine Figur erscheint als fast
identische Kopie ein zweites Mal - bekanntes "Twinning"-Problem bei
Turbo/Lightning-Checkpoints ausserhalb ihrer trainierten Aufloesung). Bei
512x512 (naeher an SDXL-Turbos eigentlicher Trainingsaufloesung) trat das
im Test nicht auf, UND die Generierung war 3-4x schneller (~20s statt
~70-95s) - siehe STANDARD_WIDTH/STANDARD_HEIGHT unten. Hoeheres CFG wurde
ebenfalls getestet und verworfen: macht das Bild uebersaettigt/"verbrannt"
(SDXL-Turbo ist explizit auf CFG=1 distilliert), ohne die Verdopplung zu
beheben.
"""
from __future__ import annotations

import base64
import json

import httpx

# sd-servers OpenAI-kompatibler Endpunkt kennt kein eigenes JSON-Feld fuer
# negative_prompt/sample_steps (siehe routes_openai.cpp im
# stable-diffusion.cpp-Repo - geparst werden nur "prompt", "n", "size",
# "output_format", "output_compression"). Zusaetzliche SDGenerationParams-
# Felder werden stattdessen ueber ein in den Prompt-Text eingebettetes
# "<sd_cpp_extra_args>{...}</sd_cpp_extra_args>"-JSON durchgereicht (per
# Regex aus dem Prompt herausgeloest, siehe common.cpp:
# extract_and_remove_sd_cpp_extra_args/SDGenerationParams::from_json_str -
# "negative_prompt" ist dort ein direkt geladenes Feld, "sample_steps"
# liegt verschachtelt unter "sample_params").
#
# Ohne Gegensteuerung neigt gerade das hier laufende Turbo/Distill-Modell
# (wenige Sampling-Schritte) zu Anatomie-Artefakten wie Extra-Gliedmassen,
# waechsern wirkenden/asymmetrischen Gesichtern (nach Haenden das
# zweitschwerste fuer Diffusionsmodelle) und bei Mehrpersonen-Szenen zu
# "Subjekt-Verdopplung" (eine Figur taucht als fast identische Kopie ein
# zweites Mal auf). Eine rein positive/vermeidende Prompt-Formulierung wie
# "strictly one pair of arms" oder "keine Gesichter im Vordergrund" hilft
# kaum, weil Diffusionsmodelle Negationen im Prompt nicht zuverlaessig
# verstehen. Bewusst als fester, immer mitgeschickter Standard-Satz statt
# als vom User editierbares Feld: die Artefaktklasse ist modellbedingt,
# nicht geschichtenspezifisch. "duplicate person"/"cloned figure"/"twins"
# zielen bewusst auf IDENTISCHE Doppelgaenger, nicht auf Personenzahl
# allgemein - echte Mehrpersonen-/Gruppenszenen sollen dadurch nicht
# beeintraechtigt werden.
NEGATIV_PROMPT_STANDARD = (
    "extra limbs, extra arms, extra hands, extra legs, extra fingers, "
    "fused fingers, missing fingers, deformed hands, mutated hands, "
    "malformed limbs, disfigured, duplicate body parts, bad anatomy, "
    "uncanny face, asymmetric face, deformed face, distorted face, "
    "waxy skin, empty stare, dead eyes, "
    "duplicate person, cloned figure, twins, identical duplicate, "
    "blurry, low quality, watermark, text"
)

# Verdoppelt gegenueber dem serverseitigen Turbo-Standard (4) - Kompromiss
# aus spuerbar besserer Anatomie/Haende und Wartezeit (siehe Live-Test oben:
# ~54s bei 4 Steps, >180s bei 30 Steps). Bei Bedarf hier zentral anpassen,
# statt in jedem Aufrufer einzeln.
STANDARD_SAMPLE_STEPS = 8

# Statt der Server-Standardaufloesung 1024x1024 (siehe Modul-Kommentar oben -
# dort trat die Subjekt-Verdopplung auf). Fuer ein Buchcover, das ohnehin
# skaliert wird (siehe app/core/pdf_export.py), ist die geringere Aufloesung
# kein spuerbarer Nachteil.
STANDARD_WIDTH = 512
STANDARD_HEIGHT = 512


class BildGenerierungFehler(Exception):
    pass


def _prompt_mit_extra_args(prompt: str, negativ_prompt: str, sample_steps: int | None,
                            width: int | None, height: int | None) -> str:
    """Haengt negativ_prompt/sample_steps/width/height als eingebettetes
    sd_cpp_extra_args-JSON an den Prompt an (siehe Modul-Kommentare oben) -
    json.dumps statt manuellem String-Bau, damit Anfuehrungszeichen im
    Prompt/Negativ-Prompt korrekt escaped werden."""
    extra_args: dict = {}
    if negativ_prompt:
        extra_args["negative_prompt"] = negativ_prompt
    if sample_steps is not None:
        extra_args["sample_params"] = {"sample_steps": sample_steps}
    if width is not None:
        extra_args["width"] = width
    if height is not None:
        extra_args["height"] = height
    if not extra_args:
        return prompt
    return f"{prompt}\n<sd_cpp_extra_args>{json.dumps(extra_args, ensure_ascii=False)}</sd_cpp_extra_args>"


async def generiere_cover(base_url: str, prompt: str, timeout: float = 120.0,
                           negativ_prompt: str = NEGATIV_PROMPT_STANDARD,
                           sample_steps: int | None = STANDARD_SAMPLE_STEPS,
                           width: int | None = STANDARD_WIDTH,
                           height: int | None = STANDARD_HEIGHT) -> bytes:
    """Ruft sd-servers OpenAI-kompatiblen Endpunkt auf (siehe
    examples/server/routes_openai.cpp im stable-diffusion.cpp-Repo) und
    liefert die rohen PNG-Bytes des ersten (einzigen) Ergebnisbilds.
    negativ_prompt/sample_steps/width/height werden als sd_cpp_extra_args in
    den Prompt eingebettet (siehe _prompt_mit_extra_args) - jeweils
    None/leer lassen, um den sd-server-Standard zu verwenden. timeout auf
    120s zurueckgesetzt: 512x512 dauerte im Live-Test nur ~20s, 120s laesst
    trotzdem grosszuegig Puffer fuer langsamere Durchlaeufe."""
    gesamt_prompt = _prompt_mit_extra_args(prompt, negativ_prompt, sample_steps, width, height)
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
