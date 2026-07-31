import asyncio
import json as jsonlib

import httpx
import pytest

from app.core import ollama_client
from app.core.ollama_client import OllamaFehler, chat_stream


class _FakeStreamAntwort:
    def __init__(self, status_code: int, zeilen: list[str] | None = None, body: bytes = b""):
        self.status_code = status_code
        self._zeilen = zeilen or []
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aread(self):
        return self._body

    async def aiter_lines(self):
        for zeile in self._zeilen:
            yield zeile


class _FakeAsyncClient:
    """Ersetzt httpx.AsyncClient in ollama_client.chat_stream(), damit ohne
    echtes Ollama getestet werden kann, welches Modell tatsaechlich im
    Payload landet (modell_override vs. rollen.py-Default) und wie ein
    HTTP-404 (fehlendes Modell) behandelt wird."""

    letzter_payload: dict | None = None
    antwort_status = 200

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, json=None):
        _FakeAsyncClient.letzter_payload = json
        if _FakeAsyncClient.antwort_status == 404:
            return _FakeStreamAntwort(404, body=b'{"error":"model \'x\' not found"}')
        zeilen = [
            jsonlib.dumps({"message": {"content": "Hallo"}, "done": False}),
            jsonlib.dumps({"message": {}, "done": True, "eval_duration": 1_000_000_000, "eval_count": 5}),
        ]
        return _FakeStreamAntwort(200, zeilen=zeilen)


@pytest.fixture(autouse=True)
def _fake_httpx(monkeypatch):
    _FakeAsyncClient.letzter_payload = None
    _FakeAsyncClient.antwort_status = 200
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)


async def _sammle(rolle="lektor", modell_override=None):
    events = []
    async for event in chat_stream("http://fake", rolle, "system", "user", modell_override=modell_override):
        events.append(event)
    return events


def test_ohne_override_wird_rollen_default_verwendet():
    asyncio.run(_sammle())
    assert _FakeAsyncClient.letzter_payload["model"] == ollama_client.ROLLEN["lektor"]["modell"]


def test_modell_override_ueberschreibt_rollen_default():
    asyncio.run(_sammle(modell_override="qwen3:14b"))
    assert _FakeAsyncClient.letzter_payload["model"] == "qwen3:14b"


def test_404_erzeugt_sprechende_fehlermeldung_mit_modellname():
    _FakeAsyncClient.antwort_status = 404

    async def _lauf():
        with pytest.raises(OllamaFehler) as exc_info:
            await _sammle(modell_override="verschwunden:1b")
        return exc_info

    exc_info = asyncio.run(_lauf())
    text = str(exc_info.value)
    assert "verschwunden:1b" in text
    assert "nicht verfügbar" in text
