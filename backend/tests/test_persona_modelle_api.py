import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import passwort_hashen
from app.config import Settings, get_settings
from app.core.rollen import ROLLEN
from app.db import init_db
from app.main import app
from app.services import ollama_basis_url, rollen_modell_override


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


def _ziel(settings, name="PC", host="http://127.0.0.1:11434"):
    return db.ssh_ziel_anlegen(
        settings.database_path, settings.secret_key_path, name=name, host=host,
        port=22, username="", auth_method="direct", geheimnis={}, remote_ollama_port=11434,
    )


@pytest.fixture
def ziel_id(client):
    return _ziel(app.dependency_overrides[get_settings]())


def test_liste_ohne_login_liefert_401(auth_client):
    r = auth_client.get("/api/persona-modelle", params={"ziel_id": "x"})
    assert r.status_code == 401


def test_liste_als_nicht_admin_liefert_403(auth_client):
    _login(auth_client, "mitschreiber")
    r = auth_client.get("/api/persona-modelle", params={"ziel_id": "x"})
    assert r.status_code == 403


def test_setzen_als_nicht_admin_liefert_403(auth_client):
    _login(auth_client, "mitschreiber")
    r = auth_client.put("/api/persona-modelle/lektor", params={"ziel_id": "x"}, json={"modell": "qwen3:14b"})
    assert r.status_code == 403


def test_liste_ohne_ziel_id_liefert_422(client):
    assert client.get("/api/persona-modelle").status_code == 422


def test_unbekanntes_ziel_liefert_404(client):
    assert client.get("/api/persona-modelle", params={"ziel_id": "gibt-es-nicht"}).status_code == 404
    r = client.put("/api/persona-modelle/lektor", params={"ziel_id": "gibt-es-nicht"}, json={"modell": "m"})
    assert r.status_code == 404


def test_liste_zeigt_alle_rollen_ohne_override(client, ziel_id):
    r = client.get("/api/persona-modelle", params={"ziel_id": ziel_id})
    assert r.status_code == 200
    daten = {e["persona"]: e for e in r.json()}
    assert set(daten.keys()) == set(ROLLEN.keys())
    for persona, cfg in ROLLEN.items():
        assert daten[persona]["default_modell"] == cfg["modell"]
        assert daten[persona]["override_modell"] is None
        assert daten[persona]["effektives_modell"] == cfg["modell"]


def test_setzen_ueberschreibt_effektives_modell(client, ziel_id):
    r = client.put("/api/persona-modelle/lektor", params={"ziel_id": ziel_id}, json={"modell": "qwen3:14b"})
    assert r.status_code == 200
    daten = r.json()
    assert daten["override_modell"] == "qwen3:14b"
    assert daten["effektives_modell"] == "qwen3:14b"
    assert daten["default_modell"] == ROLLEN["lektor"]["modell"]

    r2 = client.get("/api/persona-modelle", params={"ziel_id": ziel_id})
    lektor = next(e for e in r2.json() if e["persona"] == "lektor")
    assert lektor["override_modell"] == "qwen3:14b"


def test_setzen_mit_leerem_modell_loescht_override(client, ziel_id):
    client.put("/api/persona-modelle/lektor", params={"ziel_id": ziel_id}, json={"modell": "qwen3:14b"})
    r = client.put("/api/persona-modelle/lektor", params={"ziel_id": ziel_id}, json={"modell": None})
    assert r.status_code == 200
    daten = r.json()
    assert daten["override_modell"] is None
    assert daten["effektives_modell"] == ROLLEN["lektor"]["modell"]


def test_setzen_fuer_unbekannte_persona_gibt_404(client, ziel_id):
    r = client.put("/api/persona-modelle/nicht_vorhanden", params={"ziel_id": ziel_id}, json={"modell": "irgendwas"})
    assert r.status_code == 404


def test_andere_personas_bleiben_von_override_unberuehrt(client, ziel_id):
    client.put("/api/persona-modelle/lektor", params={"ziel_id": ziel_id}, json={"modell": "qwen3:14b"})
    r = client.get("/api/persona-modelle", params={"ziel_id": ziel_id})
    daten = {e["persona"]: e for e in r.json()}
    assert daten["autor"]["effektives_modell"] == ROLLEN["autor"]["modell"]
    assert daten["autor"]["override_modell"] is None


def test_override_gilt_nur_auf_dem_gesetzten_ziel(client, ziel_id):
    settings = app.dependency_overrides[get_settings]()
    anderes = _ziel(settings, name="Athene", host="http://192.168.0.5:11434")
    client.put("/api/persona-modelle/autor", params={"ziel_id": ziel_id}, json={"modell": "xs"})

    pc = {e["persona"]: e for e in client.get("/api/persona-modelle", params={"ziel_id": ziel_id}).json()}
    athene = {e["persona"]: e for e in client.get("/api/persona-modelle", params={"ziel_id": anderes}).json()}
    assert pc["autor"]["effektives_modell"] == "xs"
    assert athene["autor"]["effektives_modell"] == ROLLEN["autor"]["modell"]
    assert athene["autor"]["override_modell"] is None


def test_aufloesung_folgt_dem_aktiven_ki_ziel(client, ziel_id):
    settings = app.dependency_overrides[get_settings]()
    anderes = _ziel(settings, name="Athene", host="http://192.168.0.5:11434")
    db.persona_modell_schreiben(settings.database_path, ziel_id, "autor", "xs")

    assert rollen_modell_override(settings, "autor") is None  # kein Ziel aktiv
    with ollama_basis_url(settings, ziel_id):
        assert rollen_modell_override(settings, "autor") == "xs"
    with ollama_basis_url(settings, anderes):
        assert rollen_modell_override(settings, "autor") is None
    with ollama_basis_url(settings, None):
        assert rollen_modell_override(settings, "autor") is None
    assert rollen_modell_override(settings, "autor") is None  # wieder zurueckgesetzt


def test_ziel_loeschen_entfernt_dessen_zuordnung(client, ziel_id):
    settings = app.dependency_overrides[get_settings]()
    db.persona_modell_schreiben(settings.database_path, ziel_id, "autor", "xs")
    db.ssh_ziel_loeschen(settings.database_path, ziel_id)
    assert db.persona_modelle_alle_lesen(settings.database_path, ziel_id) == {}


def test_migration_kopiert_alte_globale_zuordnung_auf_alle_ziele(tmp_path):
    pfad = tmp_path / "novelle_gui.db"
    schluessel = tmp_path / ".secret_key"
    init_db(pfad)
    a = db.ssh_ziel_anlegen(pfad, schluessel, name="A", host="http://a:11434", port=22, username="",
                            auth_method="direct", geheimnis={}, remote_ollama_port=11434)
    b = db.ssh_ziel_anlegen(pfad, schluessel, name="B", host="http://b:11434", port=22, username="",
                            auth_method="direct", geheimnis={}, remote_ollama_port=11434)
    with sqlite3.connect(pfad) as conn:
        conn.execute("INSERT INTO persona_modelle (persona, modell, updated_at) VALUES ('lektor', 'm1', 't')")

    init_db(pfad)
    assert db.persona_modell_lesen(pfad, a, "lektor") == "m1"
    assert db.persona_modell_lesen(pfad, b, "lektor") == "m1"

    # Nach der Migration ist die Alt-Tabelle leer; ein spaeter geloeschter
    # Override kommt beim naechsten Start nicht wieder zurueck.
    db.persona_modell_loeschen(pfad, a, "lektor")
    init_db(pfad)
    assert db.persona_modell_lesen(pfad, a, "lektor") is None
    assert db.persona_modell_lesen(pfad, b, "lektor") == "m1"
