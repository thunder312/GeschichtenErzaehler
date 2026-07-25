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
def projekt_mit_titel_und_kapitel(client, tmp_path):
    r = client.post("/api/projects", json={"titel": "", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    antwort = client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDer Nebelmarkt\n",
    })
    aktueller_ordner = antwort.json()["neuer_ordner"] or ordner
    projekt_pfad = tmp_path / "projects" / "daniel" / aktueller_ordner / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "Ein Kapiteltext.")
    return aktueller_ordner


def test_export_schreibt_datei_mit_titel_statt_gesamt_md(client, projekt_mit_titel_und_kapitel, tmp_path):
    ordner = projekt_mit_titel_und_kapitel
    assert ordner == "Der-Nebelmarkt"  # Regression: Umbenennung muss ueberhaupt geklappt haben

    r = client.post(f"/api/projects/{ordner}/export")
    assert r.status_code == 200
    assert r.json()["dateiname"] == "Der-Nebelmarkt.md"

    story_root = tmp_path / "projects" / "daniel" / ordner
    assert (story_root / "Der-Nebelmarkt.md").exists()
    assert not (story_root / "gesamt.md").exists()


def test_gesamt_lesen_findet_datei_unter_titel_namen(client, projekt_mit_titel_und_kapitel):
    ordner = projekt_mit_titel_und_kapitel
    client.post(f"/api/projects/{ordner}/export")

    r = client.get(f"/api/projects/{ordner}/gesamt")
    assert r.status_code == 200
    assert "Ein Kapiteltext." in r.text


def test_export_raeumt_veraltete_gesamt_md_auf(client, projekt_mit_titel_und_kapitel, tmp_path):
    ordner = projekt_mit_titel_und_kapitel
    story_root = tmp_path / "projects" / "daniel" / ordner
    (story_root / "gesamt.md").write_text("Alter Export.", encoding="utf-8")

    client.post(f"/api/projects/{ordner}/export")

    assert not (story_root / "gesamt.md").exists()
    assert (story_root / "Der-Nebelmarkt.md").exists()
