import pytest
from fastapi.testclient import TestClient

from app.api import fundus as api_fundus
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


def test_fundus_lesen_liefert_leere_vorlage_ohne_vorhandene_datei(client):
    r = client.get("/api/fundus")
    assert r.status_code == 200
    assert "FUNDUS-VORLAGE" in r.text


def test_fundus_schreiben_und_wieder_lesen(client):
    inhalt = "## Regency\n\n### Lady Amelia\n- Alter: 24\n- Geschichten: Testgeschichte\n"
    r = client.put("/api/fundus", json={"inhalt": inhalt})
    assert r.status_code == 200

    r2 = client.get("/api/fundus")
    assert r2.text.strip() == inhalt.strip()


def test_fundus_schreiben_sichert_vorherige_fassung_als_bak(client, tmp_path):
    client.put("/api/fundus", json={"inhalt": "Erste Fassung"})
    r = client.put("/api/fundus", json={"inhalt": "Zweite Fassung"})
    assert r.json()["gesichert_als"] is not None

    fundus_datei = tmp_path / "projects" / "daniel" / "fundus.md"
    assert fundus_datei.read_text(encoding="utf-8").strip() == "Zweite Fassung"
    sicherungen = list(fundus_datei.parent.glob("fundus.md.*.bak"))
    assert len(sicherungen) == 1
    assert sicherungen[0].read_text(encoding="utf-8").strip() == "Erste Fassung"


def test_fundus_import_ueberspringt_projekte_ohne_figuren_abschnitt(client):
    r = client.post("/api/projects", json={"titel": "Projekt ohne Figuren", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nOhne Figuren\n\n## Rahmen\nJahr: 1815\n",
    })

    r2 = client.post("/api/fundus/import")
    assert r2.status_code == 200
    daten = r2.json()
    assert daten["importierte_projekte"] == 0
    assert daten["gefundene_figuren"] == 0
    assert len(daten["uebersprungen"]) == 1


def test_fundus_import_extrahiert_figuren_aus_geruest(client, monkeypatch):
    r = client.post("/api/projects", json={"titel": "Der Markt von Rothenfeld", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n\n"
                  "## Figuren\nLady Amelia Hartwell, 24, Baronesse, eigensinnig.\n\n"
                  "## Konflikt\nSie will heiraten, ihr Vater verbietet es.\n",
    })

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None):
        return (
            '{"figuren": [{"name": "Lady Amelia Hartwell", "alter": "24", '
            '"stand": "Baronesse", "eigenschaften": "eigensinnig"}]}',
            {},
        )

    monkeypatch.setattr(api_fundus, "sammle_antwort", fake_sammle_antwort)

    r2 = client.post("/api/fundus/import")
    assert r2.status_code == 200
    daten = r2.json()
    assert daten["importierte_projekte"] == 1
    assert daten["gefundene_figuren"] == 1
    assert daten["uebersprungen"] == []

    r3 = client.get("/api/fundus")
    assert "## Regency" in r3.text
    assert "### Lady Amelia Hartwell" in r3.text
    assert "Der Markt von Rothenfeld" in r3.text
