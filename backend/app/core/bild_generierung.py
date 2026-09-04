"""HTTP-Anbindung an sd-server (stable-diffusion.cpp) fuer die
Deckblattbild-Generierung (siehe ToDo.md).

Analog zu app/core/ollama_client.py: base_url zeigt entweder auf ein lokales
sd-server oder auf das lokale Ende eines SSH-Tunnels (siehe
app/core/ssh_manager.py) - dieser Client weiss nichts von SSH.

Angesprochen wird die native asynchrone API von sd-server
(examples/server/api.md im stable-diffusion.cpp-Repo, Praefix /sdcpp/v1):
POST /sdcpp/v1/img_gen nimmt die Generierungsparameter als echtes,
verschachteltes JSON entgegen (prompt, negative_prompt, width, height,
sample_params.sample_steps, ...) und liefert SOFORT nur eine Job-ID zurueck
(HTTP 202). Das fertige Bild wird anschliessend per
GET /sdcpp/v1/jobs/{id} abgeholt, sobald "status" == "completed" ist -
Base64-PNG unter result.images[0].b64_json. Status-Werte laut api.md:
queued, generating, completed, failed, cancelled.

Bewusst NICHT der OpenAI-kompatible Pfad /v1/images/generations: der parst
nur prompt/n/size/output_format, fuer negative_prompt/sample_steps braucht
es dort einen bruechigen, in den Prompt-Text eingebetteten
<sd_cpp_extra_args>-Hack (den nicht jeder Server-Build auswertet). Die
native API nimmt diese Felder direkt entgegen und ist auch das, was die
mitgelieferte Web-Oberflaeche von sd-server selbst nutzt.

**Modell (Stand 2026-08-30): FLUX.1-schnell** (Q4_K_S-GGUF, Vulkan-Backend,
Text-Encoder per --clip-on-cpu ausgelagert - Setup in der Athene-Compose
~/docker/sd-server-compose.yaml). Loeste SDXL-Turbo ab: das liess bei komplexen
Mehr-Personen-Prompts zuverlaessig Elemente fallen (nur CLIP-Encoder +
Turbo-Distillation, Beispiel-Fehlbild: zwei geforderte Figuren -> nur eine
generiert). FLUX bringt einen T5-XXL-Encoder und damit deutlich bessere
Prompt-Treue. Konsequenzen fuer die Defaults hier:
- STANDARD_WIDTH/HEIGHT = 1024: FLUX ist auf 1024 trainiert. Die frueheren
  512x512 waren ein reiner SDXL-Turbo-Workaround gegen "Subjekt-
  Verdopplung"/"Twinning" bei 1024 - bei FLUX kein Thema.
- STANDARD_SAMPLE_STEPS = 4: FLUX.1-schnell ist auf 4 Schritte distilliert.
- CFG bleibt beim Server-Default 1.0 (schnell ist darauf distilliert).
  sd-server ignoriert den Negativ-Prompt bei cfg==1 - er wird trotzdem
  mitgeschickt, damit er automatisch greift, falls spaeter auf ein
  CFG>1-Modell (FLUX.1-dev, SD3.5) gewechselt wird.
- Generierung dauert auf der 780M-iGPU laenger als Turbo (Minuten statt
  Sekunden) -> timeout in generiere_cover() grosszuegig (600s). Achtung:
  ein evtl. nginx-proxy_read_timeout auf Prod (Default 60s) kann den
  Frontend-Request abschneiden, obwohl das Backend das Bild noch fertig
  speichert - ggf. dort erhoehen.
"""
from __future__ import annotations

import asyncio
import base64
import io
import time

import httpx
from PIL import Image, UnidentifiedImageError

# Fester, immer als negative_prompt mitgeschickter Standard-Satz gegen
# typische Diffusions-Artefakte (Extra-Gliedmassen, waechserne/asymmetrische
# Gesichter, identische Doppelgaenger). Kein vom User editierbares Feld: die
# Artefaktklasse ist modellbedingt, nicht geschichtenspezifisch. "duplicate
# person"/"cloned figure"/"twins" zielen bewusst auf IDENTISCHE
# Doppelgaenger, nicht auf die Personenzahl allgemein - echte
# Mehrpersonen-/Gruppenszenen sollen nicht beeintraechtigt werden.
# HINWEIS: Bei CFG==1 (aktuelles Modell FLUX.1-schnell) wertet sd-server den
# Negativ-Prompt gar nicht aus - er wird trotzdem gesendet, damit er bei
# einem Wechsel auf ein CFG>1-Modell (FLUX.1-dev, SD3.5) automatisch greift.
# "extra arm"/"third arm"/"three arms"/"duplicate arm"/"duplicate hand" bewusst
# zusaetzlich zu "extra arms"/"extra hands" (Plural) ergaenzt: ein Pony-
# Testbild (siehe Recherche zu PONY_LORA_PATH) zeigte trotz der Plural-Form
# eine Figur mit drei Armen - explizite Singular-/Zahlwort-Varianten treffen
# dieses konkrete Artefakt zuverlaessiger.
NEGATIV_PROMPT_STANDARD = (
    "extra limbs, extra arms, extra hands, extra legs, extra fingers, "
    "extra arm, third arm, three arms, duplicate arm, duplicate hand, "
    "fused fingers, missing fingers, deformed hands, mutated hands, "
    "malformed limbs, disfigured, duplicate body parts, bad anatomy, "
    "uncanny face, asymmetric face, deformed face, distorted face, "
    "waxy skin, empty stare, dead eyes, "
    "duplicate person, cloned figure, twins, identical duplicate, "
    "blurry, low quality, watermark, text"
)

# FLUX.1-schnell ist auf 4 Sampling-Schritte distilliert - mehr bringt kaum
# Qualitaet, kostet aber linear Zeit. (SDXL-Turbo lief hier vorher mit 8.)
# Bei Bedarf hier zentral anpassen, statt in jedem Aufrufer einzeln.
STANDARD_SAMPLE_STEPS = 4

# FLUX-Trainingsaufloesung (zugleich der -W/-H-Default in der Athene-Compose).
# Das Buchcover wird fuer den PDF-Export (app/core/pdf_export.py) ohnehin
# skaliert. Frueher 512x512 - reiner SDXL-Turbo-Workaround gegen Twinning.
STANDARD_WIDTH = 1024
STANDARD_HEIGHT = 1024

# Wie oft der Job-Status abgefragt wird, waehrend sd-server rechnet. 3s: FLUX
# auf der 780M-iGPU braucht Minuten, haeufigeres Pollen brauchte nur den
# SSH-Tunnel (siehe app/core/ssh_manager.py) unnoetig unter Last.
POLL_INTERVALL_S = 3.0

# Zweites Bildmodell (siehe app/services.py:bild_basis_url, modell="pony"):
# Pony Diffusion V6 XL (GGUF Q8_0) + "Realism LoRA by Stable Yogi" - eigene,
# unabhaengige sd-server-Instanz auf Athene (Port in bildki_port_pony, siehe
# app/db.py), fuer fotorealistische Cover ohne die Content-Einschraenkung aus
# g.COVER_PROMPT_SYSTEM (die gilt nur fuer den AUTOMATISCHEN deutschen
# Prompt-Vorschlag, nicht fuer einen vom User selbst eingetippten Prompt -
# siehe app/api/pipeline.py:cover_prompt_vorschlagen/cover_generieren).
# Anders als FLUX.1-schnell ist Pony KEIN Turbo-Modell: braucht echtes CFG
# und mehr Schritte, dafuer wirkt der Negativ-Prompt hier tatsaechlich.
# Werte entsprechen der Compose-Konfiguration auf Athene
# (~/docker/sd-server-pony-compose.yaml) bzw. der Empfehlung im GGUF-Repo
# (offgrid-ai/pony-diffusion-v6-xl-GGUF).
PONY_SAMPLE_STEPS = 24
PONY_CFG_SCALE = 5.0
PONY_SAMPLE_METHOD = "dpm++2m"

# Dateiname relativ zu --lora-model-dir auf der Pony-sd-server-Instanz (siehe
# GET /sdcpp/v1/capabilities -> "loras"). Gewicht 1.0 liegt in der von
# Stable Yogi empfohlenen Spanne 0.4-1.5.
PONY_LORA_PATH = "Realism Lora By Stable Yogi_V3_Lite.safetensors"
PONY_LORA_MULTIPLIER = 1.0

# Pony Diffusion wurde mit einem Aesthetic-Score-System trainiert: ohne diese
# absteigende Tag-Kette am Prompt-Anfang wirken Bilder flau/unfertig (siehe
# Recherche zu Pony-Diffusion-Prompting). Rein technische Tokens ohne
# Bedeutung fuer den User - werden NICHT im editierbaren deutschen/englischen
# Prompt-Feld angezeigt, sondern erst hier unmittelbar vor der Anfrage an
# sd-server ergaenzt.
PONY_SCORE_TAGS_PRAEFIX = (
    "score_9, score_8_up, score_7_up, score_6_up, score_5_up, score_4_up, "
)


def cover_generierung_parameter(modell: str, prompt_englisch: str) -> dict:
    """Liefert die Zusatz-Keyword-Argumente fuer generiere_cover() (sample_steps/
    sample_method/cfg_scale/lora) sowie den ggf. um PONY_SCORE_TAGS_PRAEFIX
    ergaenzten Prompt - je nach vom User gewaehltem Bildmodell ("flux"
    (Standard) oder "pony", siehe app/schemas.py:CoverGenerierenAnfrage.bild_modell
    und app/services.py:bild_basis_url). Ergebnis-Dict passt per **-Entpackung
    direkt auf generiere_cover(base_url=..., **ergebnis)."""
    if modell == "pony":
        return {
            "prompt": PONY_SCORE_TAGS_PRAEFIX + prompt_englisch,
            "sample_steps": PONY_SAMPLE_STEPS,
            "sample_method": PONY_SAMPLE_METHOD,
            "cfg_scale": PONY_CFG_SCALE,
            "lora": [{"path": PONY_LORA_PATH, "multiplier": PONY_LORA_MULTIPLIER}],
        }
    return {
        "prompt": prompt_englisch,
        "sample_steps": STANDARD_SAMPLE_STEPS,
        "sample_method": None,
        "cfg_scale": None,
        "lora": None,
    }


class BildGenerierungFehler(Exception):
    pass


# Grosszuegige Obergrenze fuer ein manuell hochgeladenes Titelbild - schuetzt
# vor versehentlichem Upload einer riesigen Datei, nicht vor Missbrauch
# (dafuer reicht bei einer Handvoll eingeloggter Nutzer kein Rate-Limit).
COVER_UPLOAD_MAX_BYTES = 15 * 1024 * 1024


def cover_aus_upload_normalisieren(rohdaten: bytes, max_bytes: int = COVER_UPLOAD_MAX_BYTES) -> bytes:
    """Validiert ein manuell hochgeladenes Titelbild (siehe app/api/pipeline.py:
    cover_hochladen - Alternative zur KI-Generierung weiter unten in dieser
    Datei, z.B. wenn ein Bild von Hand ueber eine kostenlose Web-Oberflaeche
    wie Google AI Studio erzeugt und hier nur noch eingebunden werden soll)
    und wandelt es in PNG-Bytes um, damit cover.png (siehe
    app/core/projekt_dateien.py:cover_datei) unabhaengig vom hochgeladenen
    Ausgangsformat (JPEG, WEBP, ...) immer im selben Format vorliegt - sowohl
    cover_lesen() (media_type="image/png") als auch der PDF-Export
    (app/core/pdf_export.py:ImageReader) erwarten das nicht zwingend, aber
    ein einheitliches Format vermeidet ueberraschende Sonderfaelle.
    Pillow entschaerft Dekompressions-Bomben bereits selbst (Image.
    MAX_IMAGE_PIXELS), die Byte-Obergrenze hier greift zusaetzlich VOR jedem
    Dekodierversuch."""
    if len(rohdaten) > max_bytes:
        raise BildGenerierungFehler(
            f"Datei ist zu groß ({len(rohdaten) / 1_000_000:.1f} MB, "
            f"erlaubt sind maximal {max_bytes / 1_000_000:.0f} MB)."
        )
    try:
        bild = Image.open(io.BytesIO(rohdaten))
        bild = bild.convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise BildGenerierungFehler(
            "Datei konnte nicht als Bild gelesen werden (kein gültiges "
            "PNG/JPEG/WEBP oder beschädigt)."
        ) from e
    puffer = io.BytesIO()
    bild.save(puffer, format="PNG")
    return puffer.getvalue()


def _job_payload(prompt: str, negativ_prompt: str, sample_steps: int | None,
                 width: int | None, height: int | None,
                 sample_method: str | None = None, cfg_scale: float | None = None,
                 lora: list[dict] | None = None) -> dict:
    """Baut den Request-Body fuer POST /sdcpp/v1/img_gen. Felder, die None/leer
    sind, werden weggelassen, damit sd-server jeweils seinen eigenen Default
    verwendet (siehe examples/server/api.md). sample_method/cfg_scale landen
    beide unter sample_params (cfg_scale als sample_params.guidance.txt_cfg),
    lora ist ein eigenes Top-Level-Feld (Liste von {"path", "multiplier"},
    NICHT die <lora:...>-Prompt-Syntax der CLI - siehe Pony-Recherche in
    app/core/bild_generierung.py:PONY_LORA_PATH)."""
    payload: dict = {"prompt": prompt, "output_format": "png"}
    if negativ_prompt:
        payload["negative_prompt"] = negativ_prompt
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height
    if lora:
        payload["lora"] = lora
    sample_params: dict = {}
    if sample_steps is not None:
        sample_params["sample_steps"] = sample_steps
    if sample_method is not None:
        sample_params["sample_method"] = sample_method
    if cfg_scale is not None:
        sample_params["guidance"] = {"txt_cfg": cfg_scale}
    if sample_params:
        payload["sample_params"] = sample_params
    return payload


async def generiere_cover(base_url: str, prompt: str, timeout: float = 600.0,
                           negativ_prompt: str = NEGATIV_PROMPT_STANDARD,
                           sample_steps: int | None = STANDARD_SAMPLE_STEPS,
                           width: int | None = STANDARD_WIDTH,
                           height: int | None = STANDARD_HEIGHT,
                           sample_method: str | None = None,
                           cfg_scale: float | None = None,
                           lora: list[dict] | None = None) -> bytes:
    """Startet einen Bild-Job auf sd-server (POST /sdcpp/v1/img_gen), pollt
    ihn bis "completed" (GET /sdcpp/v1/jobs/{id}) und liefert die rohen
    PNG-Bytes des ersten (einzigen) Ergebnisbilds.
    negativ_prompt/sample_steps/width/height/sample_method/cfg_scale/lora
    jeweils None bzw. leer lassen, um den sd-server-Default zu verwenden (bei
    FLUX reicht das; fuer Pony liefert
    app/core/bild_generierung.py:cover_generierung_parameter() passende
    Werte). timeout ist das Gesamt-Zeitbudget fuer Start UND Fertigstellung;
    laeuft es ab, wird BildGenerierungFehler geworfen (der Job kann
    serverseitig weiterlaufen)."""
    payload = _job_payload(prompt, negativ_prompt, sample_steps, width, height,
                            sample_method, cfg_scale, lora)
    frist = time.monotonic() + timeout
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            start = await client.post(f"{base_url}/sdcpp/v1/img_gen", json=payload)
            if start.status_code >= 400:
                raise BildGenerierungFehler(
                    f"sd-server lehnt den Bild-Job ab (HTTP {start.status_code}): "
                    f"{start.text[:500]}"
                )
            job_id = (start.json() or {}).get("id")
            if not job_id:
                raise BildGenerierungFehler(
                    f"sd-server hat keine Job-ID geliefert: {start.text[:500]}"
                )
            job_url = f"{base_url}/sdcpp/v1/jobs/{job_id}"

            while True:
                stand = await client.get(job_url)
                if stand.status_code >= 400:
                    raise BildGenerierungFehler(
                        f"Job-Status von sd-server nicht abrufbar (HTTP "
                        f"{stand.status_code}): {stand.text[:500]}"
                    )
                daten = stand.json() or {}
                status = str(daten.get("status", "")).lower()
                if status == "completed":
                    return _bild_aus_job(daten)
                if status in ("failed", "cancelled", "canceled"):
                    meldung = (daten.get("error") or {}).get("message") or status
                    raise BildGenerierungFehler(f"sd-server-Job fehlgeschlagen: {meldung}")
                if time.monotonic() >= frist:
                    raise BildGenerierungFehler(
                        f"sd-server wurde nach {timeout:.0f}s nicht fertig "
                        f"(letzter Status: {status or 'unbekannt'})."
                    )
                await asyncio.sleep(POLL_INTERVALL_S)
    except httpx.HTTPError as e:
        raise BildGenerierungFehler(
            f"sd-server nicht erreichbar unter {base_url}: {e}. Laeuft der "
            f"Container? Bei einem entfernten Ziel: SSH-Verbindung/Tunnel "
            f"pruefen."
        ) from e


def _bild_aus_job(job: dict) -> bytes:
    """Zieht das erste Ergebnisbild aus einem abgeschlossenen Job-Objekt
    (result.images[0].b64_json, siehe examples/server/api.md)."""
    bilder = (job.get("result") or {}).get("images") or []
    if not bilder or not bilder[0].get("b64_json"):
        raise BildGenerierungFehler("sd-server-Job ist fertig, enthält aber kein Bild.")
    try:
        return base64.b64decode(bilder[0]["b64_json"])
    except (ValueError, TypeError) as e:
        raise BildGenerierungFehler(f"Bilddaten von sd-server nicht dekodierbar: {e}") from e
