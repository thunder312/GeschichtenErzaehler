import pytest
from fastapi.testclient import TestClient

from app.api import pipeline as api_pipeline
from app.config import Settings, get_settings
from app.core import projekt_dateien as pd
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
    r = client.post("/api/projects", json={"titel": "Der Markt von Rothenfeld", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\n\n## Figuren\nMira, 20 Jahre.\n",
    })
    return ordner


def _projekt_pfad(tmp_path, ordner):
    return tmp_path / "projects" / "daniel" / ordner / "projekt"


def test_frage_ohne_kapitel_nutzt_platzhalter_stand(client, projekt, monkeypatch):
    gesehen = {}

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        gesehen["system"] = system
        gesehen["user"] = user
        return "Mira ist 20 Jahre alt.", {}

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)

    r = client.post(f"/api/projects/{projekt}/frage", json={"frage": "Wie alt ist Mira?"})
    assert r.status_code == 200
    assert r.json() == {"antwort": "Mira ist 20 Jahre alt."}
    assert "Noch keine Kapitel geschrieben" in gesehen["user"]
    assert "Wie alt ist Mira?" in gesehen["user"]
    assert "STORY-GERUEST" in gesehen["user"]


def test_frage_bevorzugt_stand_vor_rohem_kapiteltext(client, projekt, monkeypatch, tmp_path):
    projekt_pfad = _projekt_pfad(tmp_path, projekt)
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "Kapitel eins: Der Anfang\n\nMira betritt den Markt.")
    pd.schreib(pd.stand_datei(projekt_pfad, 1), "# STAND NACH KAPITEL 1\n\nMira steht auf dem Marktplatz.")

    gesehen = {}

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        gesehen["user"] = user
        return "Sie steht auf dem Marktplatz.", {}

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)

    r = client.post(f"/api/projects/{projekt}/frage", json={"frage": "Wo ist Mira gerade?"})
    assert r.status_code == 200
    assert "STAND NACH KAPITEL 1" in gesehen["user"]
    assert "Der Anfang" not in gesehen["user"]


def test_frage_faellt_ohne_stand_auf_rohen_kapiteltext_zurueck(client, projekt, monkeypatch, tmp_path):
    projekt_pfad = _projekt_pfad(tmp_path, projekt)
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "Kapitel eins: Der Anfang\n\nMira betritt den Markt.")

    gesehen = {}

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        gesehen["user"] = user
        return "Sie betritt den Markt.", {}

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)

    r = client.post(f"/api/projects/{projekt}/frage", json={"frage": "Wo ist Mira?"})
    assert r.status_code == 200
    assert "Mira betritt den Markt" in gesehen["user"]


def test_frage_ohne_geruest_liefert_404(client):
    r = client.post("/api/projects", json={"titel": "Leeres Projekt", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    r2 = client.post(f"/api/projects/{ordner}/frage", json={"frage": "Wer ist die Hauptfigur?"})
    assert r2.status_code == 404


def test_frage_leerer_text_liefert_422(client, projekt):
    r = client.post(f"/api/projects/{projekt}/frage", json={"frage": ""})
    assert r.status_code == 422
