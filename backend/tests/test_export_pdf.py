import pytest
from fastapi.testclient import TestClient

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
def projekt_mit_kapiteln(client, tmp_path):
    r = client.post("/api/projects", json={"titel": "Der Markt von Rothenfeld", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\n\n## Titel\nDer Markt von Rothenfeld\n",
    })
    projekt_pfad = tmp_path / "projects" / ordner / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "**Kapitel eins: Der Anfang**\n\nEin Testabsatz.")
    pd.schreib(pd.kapitel_datei(projekt_pfad, 2), "**Kapitel zwei: Die Wendung**\n\nEin weiterer Absatz.")
    return ordner


def test_export_pdf_liefert_gueltiges_pdf(client, projekt_mit_kapiteln):
    r = client.get(f"/api/projects/{projekt_mit_kapiteln}/export/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_export_pdf_ohne_kapitel_liefert_404(client):
    r = client.post("/api/projects", json={"titel": "Leeres Projekt", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    r2 = client.get(f"/api/projects/{ordner}/export/pdf")
    assert r2.status_code == 404
