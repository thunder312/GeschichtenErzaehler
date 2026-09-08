import asyncio

import pytest

from app.api import architekt as api_arch
from app.config import Settings
from app.core.ollama_client import ChatEvent, OllamaFehler
from app.core.rollen import ROLLEN
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

NORMALE_FRAGE = "1. Wie soll die Geschichte heissen? a) frei b) Vorgabe"


def _rollen_mitschnitt(monkeypatch, antworten: list[str]):
    """Patcht chat_stream und protokolliert (rolle, ueberschreibe) je Aufruf.
    `antworten` liefert der Reihe nach den Content der Zuege."""
    aufrufe: list[tuple[str, dict | None]] = []

    async def fake_chat_stream(*args, ueberschreibe=None, **kwargs):
        rolle = args[1]
        aufrufe.append((rolle, ueberschreibe))
        yield ChatEvent("content", text=antworten[len(aufrufe) - 1])

    monkeypatch.setattr(api_arch, "chat_stream", fake_chat_stream)
    return aufrufe


def test_zug_normale_frage_nutzt_nur_die_schlanke_rolle(settings, monkeypatch):
    aufrufe = _rollen_mitschnitt(monkeypatch, [NORMALE_FRAGE])
    ws = FakeWebSocket()
    verlauf = ["Ich: Lass uns anfangen."]

    antwort, fertig = asyncio.run(
        api_arch._zug(ws, settings, "http://fake", "persona", verlauf)
    )

    assert fertig is False
    assert "Wie soll die Geschichte heissen?" in antwort
    assert aufrufe == [("architekt_frage", None)]  # kein Finale-Zug
    # Frage wurde live gestreamt.
    assert any(n.get("typ") == "teil" for n in ws.gesendet)


def test_zug_finale_wird_mit_voller_rolle_neu_erzeugt(settings, monkeypatch):
    # Schlanke Rolle kippt ins Finale -> voller Zug erzeugt das Geruest neu.
    aufrufe = _rollen_mitschnitt(monkeypatch, [GERUEST_VOLLSTAENDIG, GERUEST_VOLLSTAENDIG])
    ws = FakeWebSocket()
    verlauf = ["Ich: Frage 13 Antwort"]

    antwort, fertig = asyncio.run(
        api_arch._zug(ws, settings, "http://fake", "persona", verlauf)
    )

    assert fertig is True
    assert antwort == GERUEST_VOLLSTAENDIG.strip()
    assert [r for r, _ in aufrufe] == ["architekt_frage", "architekt"]
    assert aufrufe[1][1] is None  # Finale-Zug ohne Retry, Standard-Budget
    assert verlauf[-1] == f"Du: {GERUEST_VOLLSTAENDIG.strip()}"
    # Ein angefangenes Geruest darf NICHT als Chat-Blase gestreamt werden.
    assert not any(n.get("typ") == "teil" for n in ws.gesendet)


def test_zug_finale_retry_mit_verdoppeltem_num_predict(settings, monkeypatch):
    aufrufe = _rollen_mitschnitt(
        monkeypatch, [GERUEST_VOLLSTAENDIG, GERUEST_OHNE_KAPITELPLAN, GERUEST_VOLLSTAENDIG]
    )
    ws = FakeWebSocket()
    verlauf = ["Ich: Frage 13 Antwort"]

    antwort, fertig = asyncio.run(
        api_arch._zug(ws, settings, "http://fake", "persona", verlauf)
    )

    assert fertig is True
    assert antwort == GERUEST_VOLLSTAENDIG.strip()
    assert [r for r, _ in aufrufe] == ["architekt_frage", "architekt", "architekt"]
    basis_num_predict = ROLLEN["architekt"]["optionen"]["num_predict"]
    assert aufrufe[1][1] is None
    assert aufrufe[2][1] == {"num_predict": basis_num_predict * 2}


def test_zug_scheitert_sichtbar_wenn_kapitelplan_auch_nach_retry_fehlt(settings, monkeypatch):
    _rollen_mitschnitt(
        monkeypatch,
        [GERUEST_OHNE_KAPITELPLAN, GERUEST_OHNE_KAPITELPLAN, GERUEST_OHNE_KAPITELPLAN],
    )
    ws = FakeWebSocket()
    verlauf = ["Ich: Frage 13 Antwort"]

    with pytest.raises(OllamaFehler):
        asyncio.run(api_arch._zug(ws, settings, "http://fake", "persona", verlauf))

    # Kein "Du: ..." wurde angehaengt - die abgeschnittene Antwort darf nicht
    # als abgeschlossenes Geruest im Verlauf landen.
    assert not any(eintrag.startswith("Du: ") for eintrag in verlauf)
    fehler_nachrichten = [n for n in ws.gesendet if n.get("phase") == "fehler"]
    assert len(fehler_nachrichten) == 1


def test_zug_volle_rolle_stellt_doch_eine_frage(settings, monkeypatch):
    # Randfall: schlanke Rolle kippt ins Finale, die volle Rolle liefert aber
    # wider Erwarten doch eine Frage - dann wie ein Frage-Zug behandeln.
    aufrufe = _rollen_mitschnitt(monkeypatch, [GERUEST_VOLLSTAENDIG, NORMALE_FRAGE])
    ws = FakeWebSocket()
    verlauf = ["Ich: Frage 13 Antwort"]

    antwort, fertig = asyncio.run(
        api_arch._zug(ws, settings, "http://fake", "persona", verlauf)
    )

    assert fertig is False
    assert "Wie soll die Geschichte heissen?" in antwort
    assert [r for r, _ in aufrufe] == ["architekt_frage", "architekt"]
