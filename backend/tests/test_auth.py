import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import passwort_hashen, passwort_pruefen
from app.config import Settings, get_settings
from app.db import init_db
from app.main import app


def test_passwort_hashen_und_pruefen_rundtrip():
    hash_ = passwort_hashen("geheim1234")
    assert passwort_pruefen("geheim1234", hash_) is True
    assert passwort_pruefen("falsch", hash_) is False


@pytest.fixture
def settings(tmp_path):
    s = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        auth_aktiv=True,
    )
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(s.database_path)
    db.benutzer_anlegen(s.database_path, "testuser", passwort_hashen("geheim1234"), ist_admin=False)
    return s


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_login_mit_richtigem_passwort_setzt_cookie_und_liefert_benutzer(client):
    r = client.post("/api/auth/login", json={"username": "testuser", "password": "geheim1234"})
    assert r.status_code == 200
    assert r.json()["username"] == "testuser"
    assert "ge_session" in r.cookies


def test_login_mit_falschem_passwort_liefert_401(client):
    r = client.post("/api/auth/login", json={"username": "testuser", "password": "falsch"})
    assert r.status_code == 401


def test_login_mit_unbekanntem_benutzer_liefert_401(client):
    r = client.post("/api/auth/login", json={"username": "nichtvorhanden", "password": "x"})
    assert r.status_code == 401


def test_me_ohne_cookie_liefert_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_nach_login_liefert_eingeloggten_benutzer(client):
    client.post("/api/auth/login", json={"username": "testuser", "password": "geheim1234"})
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "testuser"


def test_logout_invalidiert_session(client):
    client.post("/api/auth/login", json={"username": "testuser", "password": "geheim1234"})
    assert client.get("/api/auth/me").status_code == 200

    r = client.post("/api/auth/logout")
    assert r.status_code == 204

    assert client.get("/api/auth/me").status_code == 401


def test_session_laeuft_nach_max_age_ab(settings, client):
    client.post("/api/auth/login", json={"username": "testuser", "password": "geheim1234"})
    token = client.cookies.get("ge_session")

    with db._verbindung(settings.database_path) as conn:
        conn.execute(
            "UPDATE sessions SET last_seen_at = '2000-01-01T00:00:00+00:00' WHERE token=?",
            (token,),
        )

    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_projekte_ohne_cookie_liefert_401_wenn_auth_aktiv(client):
    r = client.get("/api/projects")
    assert r.status_code == 401
