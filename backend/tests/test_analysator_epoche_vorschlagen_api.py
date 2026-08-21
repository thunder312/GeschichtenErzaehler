import json

import pytest
from fastapi.testclient import TestClient

from app.api import analysator as api_an
from app.config import Settings, get_settings
from app.core.ollama_client import OllamaFehler
from app.db import init_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        epochen_dir=tmp_path / "epochen",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    settings.epochen_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


VORSCHLAG_JSON = json.dumps({
    "name": "Neo-Berlin",
    "erfunden": True,
    "beschreibung": "einer erfundenen Cyberpunk-Welt",
    "zeitraum": "Jahr 2088",
    "orte": "Neo-Berlin, Unterstadt",
    "gesellschaft": "Konzerne herrschen ueber alles.",
    "statusregel": "Wer keinen Konzern-Ausweis hat, zaehlt nicht.",
    "genre": "Cyberpunk",
    "rang_wort": "Klasse",
    "anreden": "",
    "nebenstrang_typen": "Verrat, Konzernintrige",
    "vorbild_franchise": "",
    "verbote_start": "Magie, Pferde",
})


def test_epoche_vorschlagen_liefert_geparsten_vorschlag(client, monkeypatch):
    aufrufe = []

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        aufrufe.append((rolle, system, user, format))
        return VORSCHLAG_JSON, {}

    monkeypatch.setattr(api_an, "sammle_antwort", fake_sammle_antwort)

    r = client.post("/api/analysator/epoche-vorschlagen", json={"text": "Ein Text ueber Neo-Berlin..."})

    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Neo-Berlin"
    assert body["erfunden"] is True
    assert body["genre"] == "Cyberpunk"
    assert len(aufrufe) == 1
    rolle, system, _user, format_arg = aufrufe[0]
    assert rolle == "analysator"
    assert "EPOCHE-VORSCHLAG" in system
    assert format_arg == "json"


def test_epoche_vorschlagen_erzwingt_erfunden_bei_gesetztem_franchise(client, monkeypatch):
    """Sicherheitsnetz: nennt das Modell ein Vorbild-Franchise, aber
    vergisst erfunden=true zu setzen, muss der Endpunkt das selbst
    korrigieren - sonst greift der FanFic-Hinweis in einleitungssatz_vorlage()
    nicht (siehe app/core/epoche.py)."""
    antwort = json.dumps({
        "name": "Hogwarts-Fanfic", "erfunden": False, "beschreibung": "x", "zeitraum": "x",
        "orte": "x", "gesellschaft": "x", "statusregel": "x", "vorbild_franchise": "Harry Potter",
    })

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return antwort, {}

    monkeypatch.setattr(api_an, "sammle_antwort", fake_sammle_antwort)

    r = client.post("/api/analysator/epoche-vorschlagen", json={"text": "Harry und Hermine..."})

    assert r.status_code == 200
    body = r.json()
    assert body["vorbild_franchise"] == "Harry Potter"
    assert body["erfunden"] is True


def test_epoche_vorschlagen_leerer_text_liefert_422(client):
    r = client.post("/api/analysator/epoche-vorschlagen", json={"text": ""})
    assert r.status_code == 422


def test_epoche_vorschlagen_gibt_ollama_fehler_als_502_weiter(client, monkeypatch):
    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        raise OllamaFehler("Ollama nicht erreichbar")

    monkeypatch.setattr(api_an, "sammle_antwort", fake_sammle_antwort)

    r = client.post("/api/analysator/epoche-vorschlagen", json={"text": "Text"})
    assert r.status_code == 502


def test_epoche_vorschlagen_ungueltiges_json_liefert_502(client, monkeypatch):
    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return "Das ist kein JSON.", {}

    monkeypatch.setattr(api_an, "sammle_antwort", fake_sammle_antwort)

    r = client.post("/api/analysator/epoche-vorschlagen", json={"text": "Text"})
    assert r.status_code == 502
