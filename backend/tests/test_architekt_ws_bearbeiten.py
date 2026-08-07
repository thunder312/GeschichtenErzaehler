"""End-zu-Ende-Test fuer "Schritte zurueckgehen" im Architekten-Interview
(siehe ArchitektInterviewPage.tsx + app/api/architekt.py:ws_architekt +
app/core/architekt.py:verlauf_gekuerzt_ab) - laeuft komplett ueber die echte
WebSocket-Route via TestClient, mit einem gefakten chat_stream() statt einem
echten Ollama-Aufruf, damit der Test deterministisch und schnell bleibt."""
import pytest
from fastapi.testclient import TestClient

import app.api.architekt as api_arch
from app.config import Settings, get_settings
from app.core.ollama_client import ChatEvent
from app.db import init_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def projekt(client):
    r = client.post("/api/projects", json={"titel": "Testprojekt", "epoche": "Regency"})
    assert r.status_code == 201
    return r.json()["ordner"]


# Antworten in der Reihenfolge der chat_stream()-Aufrufe: Frage 1 (initial),
# Frage 2 (nach Antwort auf Frage 1), Frage 3 (nach Antwort auf Frage 2),
# dann Frage 2-neu (nach dem Bearbeiten der Antwort auf Frage 1 - der
# Architekt sieht nur noch den gekuerzten Verlauf und stellt zwangslaeufig
# wieder "Frage 2", diesmal mit anderem Text, um im Test klar unterscheidbar
# zu sein von der urspruenglichen Frage 2).
_ANTWORTEN = [
    "Frage 1 von 15: Wie lang soll die Geschichte sein?\na) Kurz\nb) Mittel",
    "Frage 2 von 15: Wie explizit darf es werden?\na) Voll\nb) Angedeutet",
    "Frage 3 von 15: Welches Modell?",
    "Frage 2 von 15 (neu gestellt): Wie explizit diesmal?",
]


def test_bearbeite_ab_kuerzt_verlauf_und_architekt_stellt_naechste_frage_neu(client, projekt, monkeypatch):
    kontexte: list[str] = []

    async def fake_chat_stream(base_url, rolle, persona, user, **kwargs):
        kontexte.append(user)
        yield ChatEvent("content", text=_ANTWORTEN[len(kontexte) - 1])

    monkeypatch.setattr(api_arch, "chat_stream", fake_chat_stream)

    with client.websocket_connect(f"/api/projects/{projekt}/ws/architekt") as ws:
        frage1 = ws.receive_json()
        assert frage1["phase"] == "frage" and frage1["typ"] == "fertig"
        assert "Frage 1" in frage1["text"]

        ws.send_json({"eingabe": "a) Kurz"})
        frage2 = ws.receive_json()
        assert "Frage 2" in frage2["text"]

        ws.send_json({"eingabe": "a) Voll"})
        frage3 = ws.receive_json()
        assert "Frage 3" in frage3["text"]

        # Jetzt die Antwort auf Frage 1 nachtraeglich aendern. nachrichten
        # (Frontend-Sicht) sind an dieser Stelle:
        #   0: "Frage 1 ..." (Architekt)
        #   1: "a) Kurz"      (ich, das wird bearbeitet)
        #   2: "Frage 2 ..." (Architekt)
        #   3: "a) Voll"      (ich)
        #   4: "Frage 3 ..." (Architekt, noch offen)
        # -> bearbeite_ab=1 zielt auf die Antwort zu Frage 1.
        ws.send_json({"eingabe": "b) Mittel", "bearbeite_ab": 1})

        zurueckgesetzt = ws.receive_json()
        assert zurueckgesetzt["phase"] == "zurueckgesetzt"
        verlauf = zurueckgesetzt["verlauf"]
        assert verlauf[-1] == "Ich: b) Mittel"
        assert not any("a) Voll" in eintrag for eintrag in verlauf)
        assert not any("Frage 3" in eintrag for eintrag in verlauf)

        neue_frage = ws.receive_json()
        assert neue_frage["phase"] == "frage" and neue_frage["typ"] == "fertig"
        assert "neu gestellt" in neue_frage["text"]

    # Der Kontext des letzten chat_stream()-Aufrufs (fuer die neu gestellte
    # Frage 2) darf die verworfene Antwort/Frage nicht mehr enthalten, wohl
    # aber die bearbeitete Antwort.
    letzter_kontext = kontexte[-1]
    assert "a) Voll" not in letzter_kontext
    assert "Frage 3" not in letzter_kontext
    assert "b) Mittel" in letzter_kontext


def test_bearbeite_ab_mit_ungueltigem_index_meldet_fehler(client, projekt, monkeypatch):
    async def fake_chat_stream(base_url, rolle, persona, user, **kwargs):
        yield ChatEvent("content", text=_ANTWORTEN[0])

    monkeypatch.setattr(api_arch, "chat_stream", fake_chat_stream)

    with client.websocket_connect(f"/api/projects/{projekt}/ws/architekt") as ws:
        frage1 = ws.receive_json()
        assert "Frage 1" in frage1["text"]

        ws.send_json({"eingabe": "irgendwas", "bearbeite_ab": 999})
        fehler = ws.receive_json()
        assert fehler["phase"] == "fehler"
