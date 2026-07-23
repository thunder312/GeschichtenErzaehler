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


def test_verbotsliste_lesen_und_schreiben(client, projekt):
    r = client.get(f"/api/projects/{projekt}")
    assert r.status_code == 200
    assert "Verbotsliste" in r.json()["verbotsliste"]

    r2 = client.put(f"/api/projects/{projekt}/verbotsliste", json={"inhalt": "# Verbotsliste\n\nNeuer Eintrag"})
    assert r2.status_code == 200

    r3 = client.get(f"/api/projects/{projekt}")
    assert r3.json()["verbotsliste"] == "# Verbotsliste\n\nNeuer Eintrag"


def test_personas_auflisten(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas")
    assert r.status_code == 200
    namen = r.json()
    assert "architekt" in namen
    assert "autor" in namen
    assert "chronist" in namen


def test_persona_lesen_und_schreiben(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas/autor")
    assert r.status_code == 200
    assert len(r.text) > 0

    r2 = client.put(f"/api/projects/{projekt}/personas/autor", json={"inhalt": "Neue Autor-Persona"})
    assert r2.status_code == 200

    r3 = client.get(f"/api/projects/{projekt}/personas/autor")
    assert r3.text == "Neue Autor-Persona"


def test_persona_unbekannter_name_wird_abgelehnt(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas/nicht_vorhanden")
    assert r.status_code == 404

    r2 = client.put(f"/api/projects/{projekt}/personas/nicht_vorhanden", json={"inhalt": "x"})
    assert r2.status_code == 404
