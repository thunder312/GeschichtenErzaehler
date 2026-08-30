import asyncio
import base64
import io

import httpx
import pytest
from PIL import Image

from app.core import bild_generierung
from app.core.bild_generierung import (
    BildGenerierungFehler,
    NEGATIV_PROMPT_STANDARD,
    STANDARD_HEIGHT,
    STANDARD_SAMPLE_STEPS,
    STANDARD_WIDTH,
    cover_aus_upload_normalisieren,
    generiere_cover,
)

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-inhalt"
_B64_PNG = base64.b64encode(_PNG_BYTES).decode()


def _fertig_antwort(images=None):
    return _FakeAntwort(200, {
        "id": "job_1",
        "status": "completed",
        "result": {"output_format": "png", "images": images if images is not None
                   else [{"index": 0, "b64_json": _B64_PNG}]},
        "error": None,
    })


class _FakeAntwort:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Ersetzt httpx.AsyncClient in bild_generierung.generiere_cover(). Prueft
    den POST an /sdcpp/v1/img_gen und spielt danach die konfigurierte Folge
    von Job-Status-Antworten fuer /sdcpp/v1/jobs/{id} ab (die letzte wird
    wiederholt, falls oefter gepollt wird)."""

    post_url: str | None = None
    post_payload: dict | None = None
    post_antwort: _FakeAntwort | None = None
    get_urls: list[str] = []
    get_antworten: list[_FakeAntwort] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        _FakeAsyncClient.post_url = url
        _FakeAsyncClient.post_payload = json
        return _FakeAsyncClient.post_antwort

    async def get(self, url):
        _FakeAsyncClient.get_urls.append(url)
        antworten = _FakeAsyncClient.get_antworten
        return antworten.pop(0) if len(antworten) > 1 else antworten[0]


@pytest.fixture(autouse=True)
def _fake_httpx(monkeypatch):
    _FakeAsyncClient.post_url = None
    _FakeAsyncClient.post_payload = None
    _FakeAsyncClient.post_antwort = _FakeAntwort(202, {"id": "job_1", "status": "queued"})
    _FakeAsyncClient.get_urls = []
    _FakeAsyncClient.get_antworten = [_fertig_antwort()]
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    async def _kein_schlaf(_s):
        return None

    monkeypatch.setattr(bild_generierung.asyncio, "sleep", _kein_schlaf)


def test_generiere_cover_liefert_dekodierte_png_bytes():
    ergebnis = asyncio.run(generiere_cover("http://fake:7860", "a lovely cat"))
    assert ergebnis == _PNG_BYTES
    assert _FakeAsyncClient.post_url == "http://fake:7860/sdcpp/v1/img_gen"
    assert _FakeAsyncClient.get_urls == ["http://fake:7860/sdcpp/v1/jobs/job_1"]
    assert _FakeAsyncClient.post_payload["prompt"] == "a lovely cat"


def test_generiere_cover_sendet_alle_standardwerte_als_json():
    asyncio.run(generiere_cover("http://fake:7860", "a lovely cat"))
    assert _FakeAsyncClient.post_payload == {
        "prompt": "a lovely cat",
        "output_format": "png",
        "negative_prompt": NEGATIV_PROMPT_STANDARD,
        "width": STANDARD_WIDTH,
        "height": STANDARD_HEIGHT,
        "sample_params": {"sample_steps": STANDARD_SAMPLE_STEPS},
    }
    assert "extra limbs" in NEGATIV_PROMPT_STANDARD
    assert "deformed face" in NEGATIV_PROMPT_STANDARD
    assert "duplicate person" in NEGATIV_PROMPT_STANDARD
    assert STANDARD_SAMPLE_STEPS == 4  # FLUX.1-schnell ist auf 4 Schritte distilliert
    assert (STANDARD_WIDTH, STANDARD_HEIGHT) == (1024, 1024)  # FLUX-Trainingsaufloesung


def test_generiere_cover_laesst_leere_parameter_weg():
    asyncio.run(generiere_cover(
        "http://fake:7860", "a lovely cat", negativ_prompt="",
        sample_steps=None, width=None, height=None,
    ))
    assert _FakeAsyncClient.post_payload == {"prompt": "a lovely cat", "output_format": "png"}


def test_generiere_cover_erlaubt_eigene_werte():
    asyncio.run(generiere_cover(
        "http://fake:7860", "prompt", negativ_prompt="nur diese eine Sache",
        sample_steps=20, width=768, height=768,
    ))
    assert _FakeAsyncClient.post_payload == {
        "prompt": "prompt",
        "output_format": "png",
        "negative_prompt": "nur diese eine Sache",
        "width": 768,
        "height": 768,
        "sample_params": {"sample_steps": 20},
    }


def test_generiere_cover_pollt_bis_completed():
    _FakeAsyncClient.get_antworten = [
        _FakeAntwort(200, {"id": "job_1", "status": "queued", "result": None}),
        _FakeAntwort(200, {"id": "job_1", "status": "generating", "result": None}),
        _fertig_antwort(),
    ]
    ergebnis = asyncio.run(generiere_cover("http://fake:7860", "prompt"))
    assert ergebnis == _PNG_BYTES
    assert len(_FakeAsyncClient.get_urls) == 3


def test_generiere_cover_meldet_fehlgeschlagenen_job():
    _FakeAsyncClient.get_antworten = [_FakeAntwort(200, {
        "id": "job_1", "status": "failed", "result": None,
        "error": {"code": "generation_failed", "message": "generate_image returned empty results"},
    })]
    with pytest.raises(BildGenerierungFehler, match="generate_image returned empty results"):
        asyncio.run(generiere_cover("http://fake:7860", "prompt"))


def test_generiere_cover_meldet_timeout():
    # timeout=0: nach dem ersten "generating"-Poll ist die Frist sofort ueberschritten.
    _FakeAsyncClient.get_antworten = [_FakeAntwort(200, {"id": "job_1", "status": "generating", "result": None})]
    with pytest.raises(BildGenerierungFehler, match="nicht fertig"):
        asyncio.run(generiere_cover("http://fake:7860", "prompt", timeout=0.0))


def test_generiere_cover_http_fehler_beim_start():
    _FakeAsyncClient.post_antwort = _FakeAntwort(404, text="not found")
    with pytest.raises(BildGenerierungFehler, match="HTTP 404"):
        asyncio.run(generiere_cover("http://fake:7860", "prompt"))


def test_generiere_cover_ohne_job_id():
    _FakeAsyncClient.post_antwort = _FakeAntwort(202, {"status": "queued"})
    with pytest.raises(BildGenerierungFehler, match="keine Job-ID"):
        asyncio.run(generiere_cover("http://fake:7860", "prompt"))


def test_generiere_cover_completed_ohne_bild():
    _FakeAsyncClient.get_antworten = [_fertig_antwort(images=[])]
    with pytest.raises(BildGenerierungFehler, match="kein Bild"):
        asyncio.run(generiere_cover("http://fake:7860", "prompt"))


def _bild_bytes(format: str, groesse: tuple[int, int] = (32, 32)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, color=(120, 60, 200)).save(puffer, format=format)
    return puffer.getvalue()


def test_cover_aus_upload_normalisieren_akzeptiert_png():
    ergebnis = cover_aus_upload_normalisieren(_bild_bytes("PNG"))
    assert ergebnis.startswith(b"\x89PNG\r\n\x1a\n")
    # Ergebnis muss selbst wieder ein gueltiges, dekodierbares PNG sein.
    assert Image.open(io.BytesIO(ergebnis)).format == "PNG"


def test_cover_aus_upload_normalisieren_wandelt_jpeg_zu_png():
    """Handverkleinertes Titelbild kommt haeufig als JPEG von einer externen
    Quelle (z.B. aus dem Browser von Google AI Studio heruntergeladen) -
    muss trotzdem als PNG landen, damit cover_lesen() (media_type=
    "image/png") und der PDF-Export konsistent bleiben."""
    jpeg_bytes = _bild_bytes("JPEG")
    assert not jpeg_bytes.startswith(b"\x89PNG")
    ergebnis = cover_aus_upload_normalisieren(jpeg_bytes)
    assert ergebnis.startswith(b"\x89PNG\r\n\x1a\n")


def test_cover_aus_upload_normalisieren_wandelt_webp_zu_png():
    ergebnis = cover_aus_upload_normalisieren(_bild_bytes("WEBP"))
    assert ergebnis.startswith(b"\x89PNG\r\n\x1a\n")


def test_cover_aus_upload_normalisieren_lehnt_ungueltige_datei_ab():
    with pytest.raises(BildGenerierungFehler):
        cover_aus_upload_normalisieren(b"das ist eindeutig kein Bild, nur Text")


def test_cover_aus_upload_normalisieren_lehnt_zu_grosse_datei_ab():
    zu_gross = b"\x00" * (1000)
    with pytest.raises(BildGenerierungFehler):
        cover_aus_upload_normalisieren(zu_gross, max_bytes=500)
