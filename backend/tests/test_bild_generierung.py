import asyncio
import base64
import json
import re

import httpx
import pytest

from app.core.bild_generierung import (
    BildGenerierungFehler,
    NEGATIV_PROMPT_STANDARD,
    STANDARD_SAMPLE_STEPS,
    generiere_cover,
)

_EXTRA_ARGS_MUSTER = re.compile(r"<sd_cpp_extra_args>(.*?)</sd_cpp_extra_args>", re.DOTALL)


def _extra_args(gesendeter_prompt: str) -> dict:
    treffer = _EXTRA_ARGS_MUSTER.search(gesendeter_prompt)
    assert treffer, f"kein sd_cpp_extra_args-Block im Prompt gefunden: {gesendeter_prompt!r}"
    return json.loads(treffer.group(1))

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-inhalt"


class _FakeAntwort:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Ersetzt httpx.AsyncClient in bild_generierung.generiere_cover(), analog
    zu tests/test_ollama_client.py - prueft den gesendeten Prompt und wie
    Fehlerantworten von sd-server behandelt werden."""

    letzte_url: str | None = None
    letzter_payload: dict | None = None
    antwort: _FakeAntwort | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        _FakeAsyncClient.letzte_url = url
        _FakeAsyncClient.letzter_payload = json
        return _FakeAsyncClient.antwort


@pytest.fixture(autouse=True)
def _fake_httpx(monkeypatch):
    _FakeAsyncClient.letzte_url = None
    _FakeAsyncClient.letzter_payload = None
    _FakeAsyncClient.antwort = _FakeAntwort(
        200, {"data": [{"b64_json": base64.b64encode(_PNG_BYTES).decode()}]}
    )
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)


def test_generiere_cover_liefert_dekodierte_png_bytes():
    ergebnis = asyncio.run(generiere_cover("http://fake:7860", "a lovely cat"))
    assert ergebnis == _PNG_BYTES
    assert _FakeAsyncClient.letzte_url == "http://fake:7860/v1/images/generations"
    gesendeter_prompt = _FakeAsyncClient.letzter_payload["prompt"]
    assert gesendeter_prompt.startswith("a lovely cat")


def test_generiere_cover_bettet_standard_negativ_prompt_und_steps_ein():
    asyncio.run(generiere_cover("http://fake:7860", "a lovely cat"))
    extra_args = _extra_args(_FakeAsyncClient.letzter_payload["prompt"])
    assert extra_args == {
        "negative_prompt": NEGATIV_PROMPT_STANDARD,
        "sample_params": {"sample_steps": STANDARD_SAMPLE_STEPS},
    }
    assert "extra limbs" in NEGATIV_PROMPT_STANDARD
    assert "deformed face" in NEGATIV_PROMPT_STANDARD
    assert "duplicate person" in NEGATIV_PROMPT_STANDARD
    assert STANDARD_SAMPLE_STEPS > 4  # verdoppelt gegenueber dem sd-server-Turbo-Standard


def test_generiere_cover_erlaubt_eigenen_negativ_prompt():
    asyncio.run(generiere_cover("http://fake:7860", "prompt", negativ_prompt="nur diese eine Sache", sample_steps=None))
    extra_args = _extra_args(_FakeAsyncClient.letzter_payload["prompt"])
    assert extra_args == {"negative_prompt": "nur diese eine Sache"}


def test_generiere_cover_erlaubt_eigene_sample_steps():
    asyncio.run(generiere_cover("http://fake:7860", "prompt", negativ_prompt="", sample_steps=20))
    extra_args = _extra_args(_FakeAsyncClient.letzter_payload["prompt"])
    assert extra_args == {"sample_params": {"sample_steps": 20}}


def test_generiere_cover_ohne_negativ_prompt_und_steps_laesst_prompt_unveraendert():
    asyncio.run(generiere_cover("http://fake:7860", "a lovely cat", negativ_prompt="", sample_steps=None))
    assert _FakeAsyncClient.letzter_payload == {"prompt": "a lovely cat"}


def test_generiere_cover_escaped_anfuehrungszeichen_im_prompt_korrekt():
    asyncio.run(generiere_cover(
        "http://fake:7860", 'a "special" cat', negativ_prompt='contains "quotes"', sample_steps=None,
    ))
    gesendeter_prompt = _FakeAsyncClient.letzter_payload["prompt"]
    assert gesendeter_prompt.startswith('a "special" cat')
    extra_args = _extra_args(gesendeter_prompt)
    assert extra_args == {"negative_prompt": 'contains "quotes"'}


def test_http_fehlerstatus_erzeugt_bild_generierung_fehler():
    _FakeAsyncClient.antwort = _FakeAntwort(500, text="server_error")
    with pytest.raises(BildGenerierungFehler):
        asyncio.run(generiere_cover("http://fake:7860", "prompt"))


def test_leere_datenliste_erzeugt_bild_generierung_fehler():
    _FakeAsyncClient.antwort = _FakeAntwort(200, {"data": []})
    with pytest.raises(BildGenerierungFehler):
        asyncio.run(generiere_cover("http://fake:7860", "prompt"))
