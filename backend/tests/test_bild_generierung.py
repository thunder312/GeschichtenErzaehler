import asyncio
import base64

import httpx
import pytest

from app.core.bild_generierung import BildGenerierungFehler, generiere_cover

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
    assert _FakeAsyncClient.letzter_payload == {"prompt": "a lovely cat"}


def test_http_fehlerstatus_erzeugt_bild_generierung_fehler():
    _FakeAsyncClient.antwort = _FakeAntwort(500, text="server_error")
    with pytest.raises(BildGenerierungFehler):
        asyncio.run(generiere_cover("http://fake:7860", "prompt"))


def test_leere_datenliste_erzeugt_bild_generierung_fehler():
    _FakeAsyncClient.antwort = _FakeAntwort(200, {"data": []})
    with pytest.raises(BildGenerierungFehler):
        asyncio.run(generiere_cover("http://fake:7860", "prompt"))
