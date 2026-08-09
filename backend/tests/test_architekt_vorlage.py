import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
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


def test_architekt_vorlage_liefert_story_geruest_struktur(client, projekt):
    r = client.get(f"/api/projects/{projekt}/architekt-vorlage")
    assert r.status_code == 200
    vorlage = r.json()["vorlage"]
    assert "# STORY-GERUEST" in vorlage
    assert "## Rahmen" in vorlage
    # Regency-Persona-Platzhaltertext (siehe app/data/epochen/Regency/architekt.txt)
    assert "Season" in vorlage
    assert "## Regeln" not in vorlage


def test_architekt_vorlage_unbekanntes_projekt_liefert_404(client):
    r = client.get("/api/projects/nicht-vorhanden/architekt-vorlage")
    assert r.status_code == 404
