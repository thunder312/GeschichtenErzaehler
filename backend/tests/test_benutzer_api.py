import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import passwort_hashen
from app.config import Settings, get_settings
from app.db import init_db
from app.main import app
from app.services import projekte_wurzel


@pytest.fixture
def settings(tmp_path):
    s = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        auth_aktiv=True,
        default_username="daniel",
    )
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(s.database_path)
    db.benutzer_anlegen(s.database_path, "daniel", passwort_hashen("geheim1234"), ist_admin=True)
    db.benutzer_anlegen(s.database_path, "mitschreiber", passwort_hashen("geheim1234"), ist_admin=False)
    return s


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client, username, password="geheim1234"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r


def test_liste_ohne_login_liefert_401(client):
    r = client.get("/api/benutzer")
    assert r.status_code == 401


def test_liste_als_nicht_admin_liefert_403(client):
    _login(client, "mitschreiber")
    r = client.get("/api/benutzer")
    assert r.status_code == 403


def test_liste_als_admin_liefert_alle_benutzer(client):
    _login(client, "daniel")
    r = client.get("/api/benutzer")
    assert r.status_code == 200
    namen = {b["username"] for b in r.json()}
    assert namen == {"daniel", "mitschreiber"}


def test_anlegen_als_admin_funktioniert_und_legt_projektordner_an(client, settings):
    _login(client, "daniel")
    r = client.post("/api/benutzer", json={"username": "neu", "password": "geheim1234", "ist_admin": False})
    assert r.status_code == 201
    daten = r.json()
    assert daten["username"] == "neu"
    assert daten["ist_admin"] is False
    assert projekte_wurzel(settings, "neu").is_dir()


def test_anlegen_als_nicht_admin_liefert_403(client):
    _login(client, "mitschreiber")
    r = client.post("/api/benutzer", json={"username": "neu", "password": "geheim1234"})
    assert r.status_code == 403


def test_anlegen_mit_doppeltem_benutzernamen_liefert_400(client):
    _login(client, "daniel")
    r = client.post("/api/benutzer", json={"username": "mitschreiber", "password": "geheim1234"})
    assert r.status_code == 400


def test_loeschen_verschiebt_projekte_zum_default_admin(client, settings):
    ordner = projekte_wurzel(settings, "mitschreiber") / "Meine-Geschichte"
    ordner.mkdir(parents=True)
    (ordner / "geruest.md").write_text("Inhalt", encoding="utf-8")

    _login(client, "daniel")
    zeile = db.benutzer_by_username(settings.database_path, "mitschreiber")
    r = client.delete(f"/api/benutzer/{zeile['id']}")
    assert r.status_code == 204

    assert db.benutzer_by_username(settings.database_path, "mitschreiber") is None
    verschoben = projekte_wurzel(settings, "daniel") / "Meine-Geschichte"
    assert verschoben.is_dir()
    assert (verschoben / "geruest.md").read_text(encoding="utf-8") == "Inhalt"


def test_loeschen_eigenen_account_liefert_400(client, settings):
    _login(client, "daniel")
    zeile = db.benutzer_by_username(settings.database_path, "daniel")
    r = client.delete(f"/api/benutzer/{zeile['id']}")
    assert r.status_code == 400


def test_loeschen_letzten_admin_liefert_400(tmp_path):
    """Bewusst mit auth_aktiv=False (Dev-/Test-Bypass): get_current_user()
    liefert dort einen impliziten Admin (id=0), der NICHT in der benutzer-
    Tabelle steht - der Selbst-Loeschen-Check greift also nicht, und nur die
    Mindestens-ein-Admin-Pruefung verhindert, dass der letzte echte
    Admin-Account aus der DB verschwindet."""
    s = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        default_username="daniel",
    )
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(s.database_path)
    db.benutzer_anlegen(s.database_path, "daniel", passwort_hashen("geheim1234"), ist_admin=True)

    app.dependency_overrides[get_settings] = lambda: s
    with TestClient(app) as c:
        zeile = db.benutzer_by_username(s.database_path, "daniel")
        r = c.delete(f"/api/benutzer/{zeile['id']}")
    app.dependency_overrides.clear()

    assert r.status_code == 400
    assert db.benutzer_by_username(s.database_path, "daniel") is not None


def test_loeschen_als_nicht_admin_liefert_403(client, settings):
    _login(client, "mitschreiber")
    zeile = db.benutzer_by_username(settings.database_path, "daniel")
    r = client.delete(f"/api/benutzer/{zeile['id']}")
    assert r.status_code == 403
