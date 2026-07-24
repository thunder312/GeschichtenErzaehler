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


def test_lesen_liefert_standardpfad_ohne_override(client, tmp_path):
    r = client.get("/api/einstellungen")
    assert r.status_code == 200
    daten = r.json()
    assert daten["ist_standard"] is True
    assert daten["projects_dir"] == str((tmp_path / "projects").resolve())
    assert daten["standard_projects_dir"] == daten["projects_dir"]


def test_schreiben_setzt_override_und_neue_projekte_landen_dort(client, tmp_path):
    neuer_ordner = tmp_path / "anderswo" / "meine_geschichten"
    r = client.put("/api/einstellungen", json={"projects_dir": str(neuer_ordner)})
    assert r.status_code == 200
    daten = r.json()
    assert daten["ist_standard"] is False
    assert daten["projects_dir"] == str(neuer_ordner.resolve())
    assert neuer_ordner.is_dir()

    r2 = client.post("/api/projects", json={"titel": "Testprojekt", "epoche": "Regency"})
    assert r2.status_code == 201
    ordner = r2.json()["ordner"]
    assert (neuer_ordner / ordner / "projekt").is_dir()
    assert not (tmp_path / "projects" / ordner).exists()

    r3 = client.get("/api/projects")
    assert any(p["ordner"] == ordner for p in r3.json())


def test_leerer_wert_setzt_auf_standard_zurueck(client, tmp_path):
    neuer_ordner = tmp_path / "anderswo"
    client.put("/api/einstellungen", json={"projects_dir": str(neuer_ordner)})

    r = client.put("/api/einstellungen", json={"projects_dir": ""})
    assert r.status_code == 200
    daten = r.json()
    assert daten["ist_standard"] is True
    assert daten["projects_dir"] == str((tmp_path / "projects").resolve())


def test_ungueltiger_pfad_liefert_400(client):
    # NUL ist unter Windows in Pfaden nie erlaubt und laesst mkdir scheitern.
    r = client.put("/api/einstellungen", json={"projects_dir": "C:\\ung\x00ueltig"})
    assert r.status_code == 400


def test_unterordner_je_epoche_default_false(client):
    r = client.get("/api/einstellungen")
    assert r.json()["unterordner_je_epoche"] is False


def test_unterordner_je_epoche_laesst_sich_setzen_und_bleibt_gespeichert(client):
    r = client.put("/api/einstellungen", json={"unterordner_je_epoche": True})
    assert r.status_code == 200
    assert r.json()["unterordner_je_epoche"] is True

    r2 = client.get("/api/einstellungen")
    assert r2.json()["unterordner_je_epoche"] is True
