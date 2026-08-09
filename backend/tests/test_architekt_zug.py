import asyncio

import pytest

from app.api import architekt as api_arch
from app.config import Settings
from app.core.ollama_client import ChatEvent, OllamaFehler
from app.db import init_db


@pytest.fixture
def settings(tmp_path):
    s = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
    )
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(s.database_path)
    return s


class FakeWebSocket:
    def __init__(self):
        self.gesendet: list[dict] = []

    async def send_json(self, daten: dict) -> None:
        self.gesendet.append(daten)


GERUEST_VOLLSTAENDIG = (
    "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n\n"
    "## Kapitelplan\nKapitel 1: Start. 1500 Woerter.\nKapitel 2: Ende. 1600 Woerter.\n"
)

GERUEST_OHNE_KAPITELPLAN = "# STORY-GERUEST\n\n## Titel\nAbgeschnitten\n\n## Figuren\nMira, 20 Jahre.\n"


def _antwort_stream(text: str):
    async def stream(*args, ueberschreibe=None, **kwargs):
        yield ChatEvent("content", text=text)
    return stream


def test_zug_akzeptiert_vollstaendiges_geruest_ohne_retry(settings, monkeypatch):
    aufrufe = []

    async def fake_chat_stream(*args, ueberschreibe=None, **kwargs):
        aufrufe.append(ueberschreibe)
        yield ChatEvent("content", text=GERUEST_VOLLSTAENDIG)

    monkeypatch.setattr(api_arch, "chat_stream", fake_chat_stream)
    ws = FakeWebSocket()
    verlauf: list[str] = ["Ich: Frage 13 Antwort"]

    antwort, fertig = asyncio.run(
        api_arch._zug(ws, settings, "http://fake", "persona", verlauf)
    )

    assert fertig is True
    assert antwort == GERUEST_VOLLSTAENDIG.strip()
    assert len(aufrufe) == 1  # kein Retry noetig
    assert verlauf[-1] == f"Du: {GERUEST_VOLLSTAENDIG.strip()}"


def test_zug_wiederholt_mit_verdoppeltem_num_predict_bei_fehlendem_kapitelplan(settings, monkeypatch):
    antworten = [GERUEST_OHNE_KAPITELPLAN, GERUEST_VOLLSTAENDIG]
    aufrufe = []

    async def fake_chat_stream(*args, ueberschreibe=None, **kwargs):
        aufrufe.append(ueberschreibe)
        yield ChatEvent("content", text=antworten[len(aufrufe) - 1])

    monkeypatch.setattr(api_arch, "chat_stream", fake_chat_stream)
    ws = FakeWebSocket()
    verlauf: list[str] = ["Ich: Frage 13 Antwort"]

    antwort, fertig = asyncio.run(
        api_arch._zug(ws, settings, "http://fake", "persona", verlauf)
    )

    assert fertig is True
    assert antwort == GERUEST_VOLLSTAENDIG.strip()
    assert len(aufrufe) == 2
    assert aufrufe[0] is None  # erster Versuch mit Standard-Budget
    assert aufrufe[1] == {"num_predict": 8192 * 2}  # Retry mit verdoppeltem Budget


def test_zug_scheitert_sichtbar_wenn_kapitelplan_auch_nach_retry_fehlt(settings, monkeypatch):
    async def fake_chat_stream(*args, ueberschreibe=None, **kwargs):
        yield ChatEvent("content", text=GERUEST_OHNE_KAPITELPLAN)

    monkeypatch.setattr(api_arch, "chat_stream", fake_chat_stream)
    ws = FakeWebSocket()
    verlauf: list[str] = ["Ich: Frage 13 Antwort"]

    with pytest.raises(OllamaFehler):
        asyncio.run(api_arch._zug(ws, settings, "http://fake", "persona", verlauf))

    # Kein "Du: ..." wurde angehaengt - die abgeschnittene Antwort darf nicht
    # als abgeschlossenes Geruest im Verlauf landen.
    assert not any(eintrag.startswith("Du: ") for eintrag in verlauf)
    fehler_nachrichten = [n for n in ws.gesendet if n.get("phase") == "fehler"]
    assert len(fehler_nachrichten) == 1


def test_zug_normale_frage_wird_ohne_retry_akzeptiert(settings, monkeypatch):
    aufrufe = []

    async def fake_chat_stream(*args, ueberschreibe=None, **kwargs):
        aufrufe.append(ueberschreibe)
        yield ChatEvent("content", text="1. Wie soll die Geschichte heissen?")

    monkeypatch.setattr(api_arch, "chat_stream", fake_chat_stream)
    ws = FakeWebSocket()
    verlauf: list[str] = ["Ich: Lass uns anfangen."]

    antwort, fertig = asyncio.run(
        api_arch._zug(ws, settings, "http://fake", "persona", verlauf)
    )

    assert fertig is False
    assert "Wie soll die Geschichte heissen?" in antwort
    assert len(aufrufe) == 1
