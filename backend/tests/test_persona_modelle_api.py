import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import passwort_hashen
from app.config import Settings, get_settings
from app.core.rollen import ROLLEN
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
def auth_client(tmp_path):
    """Fuer die Admin-Only-Tests: auth_aktiv=True mit einem Admin- und einem
    Nicht-Admin-Benutzer, analog zu test_benutzer_api.py."""
    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        auth_aktiv=True,
        default_username="daniel",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    db.benutzer_anlegen(settings.database_path, "daniel", passwort_hashen("geheim1234"), ist_admin=True)
    db.benutzer_anlegen(settings.database_path, "mitschreiber", passwort_hashen("geheim1234"), ist_admin=False)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client, username, password="geheim1234"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r


def test_liste_ohne_login_liefert_401(auth_client):
    r = auth_client.get("/api/persona-modelle")
    assert r.status_code == 401


def test_liste_als_nicht_admin_liefert_403(auth_client):
    _login(auth_client, "mitschreiber")
    r = auth_client.get("/api/persona-modelle")
    assert r.status_code == 403


def test_setzen_als_nicht_admin_liefert_403(auth_client):
    _login(auth_client, "mitschreiber")
    r = auth_client.put("/api/persona-modelle/lektor", json={"modell": "qwen3:14b"})
    assert r.status_code == 403


def test_liste_zeigt_alle_rollen_ohne_override(client):
    r = client.get("/api/persona-modelle")
    assert r.status_code == 200
    daten = {e["persona"]: e for e in r.json()}
    assert set(daten.keys()) == set(ROLLEN.keys())
    for persona, cfg in ROLLEN.items():
        assert daten[persona]["default_modell"] == cfg["modell"]
        assert daten[persona]["override_modell"] is None
        assert daten[persona]["effektives_modell"] == cfg["modell"]


def test_setzen_ueberschreibt_effektives_modell(client):
    r = client.put("/api/persona-modelle/lektor", json={"modell": "qwen3:14b"})
    assert r.status_code == 200
    daten = r.json()
    assert daten["override_modell"] == "qwen3:14b"
    assert daten["effektives_modell"] == "qwen3:14b"
    assert daten["default_modell"] == ROLLEN["lektor"]["modell"]

    r2 = client.get("/api/persona-modelle")
    lektor = next(e for e in r2.json() if e["persona"] == "lektor")
    assert lektor["override_modell"] == "qwen3:14b"


def test_setzen_mit_leerem_modell_loescht_override(client):
    client.put("/api/persona-modelle/lektor", json={"modell": "qwen3:14b"})
    r = client.put("/api/persona-modelle/lektor", json={"modell": None})
    assert r.status_code == 200
    daten = r.json()
    assert daten["override_modell"] is None
    assert daten["effektives_modell"] == ROLLEN["lektor"]["modell"]


def test_setzen_fuer_unbekannte_persona_gibt_404(client):
    r = client.put("/api/persona-modelle/nicht_vorhanden", json={"modell": "irgendwas"})
    assert r.status_code == 404


def test_andere_personas_bleiben_von_override_unberuehrt(client):
    client.put("/api/persona-modelle/lektor", json={"modell": "qwen3:14b"})
    r = client.get("/api/persona-modelle")
    daten = {e["persona"]: e for e in r.json()}
    assert daten["autor"]["effektives_modell"] == ROLLEN["autor"]["modell"]
    assert daten["autor"]["override_modell"] is None
