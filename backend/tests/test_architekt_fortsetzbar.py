import json

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


def test_ohne_verlaufsdatei_nicht_fortsetzbar(client, projekt):
    r = client.get(f"/api/projects/{projekt}/architekt-fortsetzbar")
    assert r.status_code == 200
    assert r.json() == {"fortsetzbar": False}


def test_mit_verlaufsdatei_fortsetzbar(client, projekt, tmp_path):
    verlauf_datei = tmp_path / "projects" / projekt / "projekt" / "architekt_verlauf.json"
    verlauf_datei.write_text(
        json.dumps(["Ich: Lass uns anfangen.", "Du: Frage 1 von 10: ..."]),
        encoding="utf-8",
    )
    r = client.get(f"/api/projects/{projekt}/architekt-fortsetzbar")
    assert r.json() == {"fortsetzbar": True}


def test_leere_verlaufsdatei_nicht_fortsetzbar(client, projekt, tmp_path):
    verlauf_datei = tmp_path / "projects" / projekt / "projekt" / "architekt_verlauf.json"
    verlauf_datei.write_text("[]", encoding="utf-8")
    r = client.get(f"/api/projects/{projekt}/architekt-fortsetzbar")
    assert r.json() == {"fortsetzbar": False}


def test_defekte_verlaufsdatei_nicht_fortsetzbar(client, projekt, tmp_path):
    verlauf_datei = tmp_path / "projects" / projekt / "projekt" / "architekt_verlauf.json"
    verlauf_datei.write_text("kein json{{{", encoding="utf-8")
    r = client.get(f"/api/projects/{projekt}/architekt-fortsetzbar")
    assert r.json() == {"fortsetzbar": False}
