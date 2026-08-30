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

Wichtigster Erfahrungswert (Live-Tests gegen den echten Athene-Server,
2026-08-09/10, SDXL-Turbo-Checkpoint): bei der Server-Standardaufloesung
1024x1024 trat zuverlaessig "Subjekt-Verdopplung" auf (eine Figur erscheint
als fast identische Kopie ein zweites Mal - bekanntes "Twinning"-Problem
bei Turbo/Lightning ausserhalb ihrer trainierten Aufloesung). Bei 512x512
trat das nicht auf UND die Generierung war 3-4x schneller (~20s statt
~70-95s) - siehe STANDARD_WIDTH/STANDARD_HEIGHT. Hoeheres CFG wurde
getestet und verworfen (SDXL-Turbo ist auf CFG=1 distilliert, hoehere Werte
"verbrennen" das Bild), daher wird txt_cfg hier gar nicht gesetzt - es
bleibt beim Server-Default des jeweils geladenen Modells. Wenn hier ein
anderes (Nicht-Turbo-)Modell laeuft, sind STANDARD_WIDTH/HEIGHT/
SAMPLE_STEPS ggf. neu zu bewerten.
"""
from __future__ import annotations

import asyncio
import base64
import io
import time

import httpx
from PIL import Image, UnidentifiedImageError

# Ohne Gegensteuerung neigt gerade ein Turbo/Distill-Modell (wenige
# Sampling-Schritte) zu Anatomie-Artefakten wie Extra-Gliedmassen, waechsern
# wirkenden/asymmetrischen Gesichtern (nach Haenden das zweitschwerste fuer
# Diffusionsmodelle) und bei Mehrpersonen-Szenen zu "Subjekt-Verdopplung"
# (eine Figur taucht als fast identische Kopie ein zweites Mal auf). Eine
# rein positive/vermeidende Prompt-Formulierung hilft kaum, weil
# Diffusionsmodelle Negationen im Prompt nicht zuverlaessig verstehen -
# darum ein fester, immer als negative_prompt mitgeschickter Standard-Satz
# statt eines vom User editierbaren Feldes: die Artefaktklasse ist
# modellbedingt, nicht geschichtenspezifisch. "duplicate person"/"cloned
# figure"/"twins" zielen bewusst auf IDENTISCHE Doppelgaenger, nicht auf die
# Personenzahl allgemein - echte Mehrpersonen-/Gruppenszenen sollen dadurch
# nicht beeintraechtigt werden.
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
# aus spuerbar besserer Anatomie/Haende und Wartezeit (Live-Test: ~54s bei
# 4 Steps, >180s bei 30 Steps). Bei Bedarf hier zentral anpassen, statt in
# jedem Aufrufer einzeln.
STANDARD_SAMPLE_STEPS = 8

# Statt der Server-Standardaufloesung 1024x1024 (siehe Modul-Kommentar oben -
# dort trat die Subjekt-Verdopplung auf). Fuer ein Buchcover, das ohnehin
# skaliert wird (siehe app/core/pdf_export.py), ist die geringere Aufloesung
# kein spuerbarer Nachteil.
STANDARD_WIDTH = 512
STANDARD_HEIGHT = 512

# Wie oft der Job-Status abgefragt wird, waehrend sd-server rechnet. 1.5s ist
# ein Kompromiss: haeufig genug, dass ein fertiges 512x512-Turbo-Bild (~20s)
# nicht lange liegen bleibt, selten genug, dass der SSH-Tunnel (siehe
# app/core/ssh_manager.py) nicht unnoetig unter Poll-Last kommt.
POLL_INTERVALL_S = 1.5


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
                 width: int | None, height: int | None) -> dict:
    """Baut den Request-Body fuer POST /sdcpp/v1/img_gen. Felder, die None/leer
    sind, werden weggelassen, damit sd-server jeweils seinen eigenen Default
    verwendet (siehe examples/server/api.md)."""
    payload: dict = {"prompt": prompt, "output_format": "png"}
    if negativ_prompt:
        payload["negative_prompt"] = negativ_prompt
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height
    if sample_steps is not None:
        payload["sample_params"] = {"sample_steps": sample_steps}
    return payload


async def generiere_cover(base_url: str, prompt: str, timeout: float = 180.0,
                           negativ_prompt: str = NEGATIV_PROMPT_STANDARD,
                           sample_steps: int | None = STANDARD_SAMPLE_STEPS,
                           width: int | None = STANDARD_WIDTH,
                           height: int | None = STANDARD_HEIGHT) -> bytes:
    """Startet einen Bild-Job auf sd-server (POST /sdcpp/v1/img_gen), pollt
    ihn bis "completed" (GET /sdcpp/v1/jobs/{id}) und liefert die rohen
    PNG-Bytes des ersten (einzigen) Ergebnisbilds.
    negativ_prompt/sample_steps/width/height jeweils None bzw. leer lassen,
    um den sd-server-Default zu verwenden. timeout ist das Gesamt-Zeitbudget
    fuer Start UND Fertigstellung; laeuft es ab, wird BildGenerierungFehler
    geworfen (der Job kann serverseitig weiterlaufen)."""
    payload = _job_payload(prompt, negativ_prompt, sample_steps, width, height)
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
