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


def _passwort_ziel(**overrides):
    daten = {
        "name": "Testserver",
        "host": "192.0.2.1",
        "port": 22,
        "username": "testuser",
        "auth_method": "password",
        "password": "geheim",
        "remote_ollama_port": 11434,
    }
    daten.update(overrides)
    return daten


def test_anlegen_und_auflisten(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel())
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Testserver"
    assert "secret_encrypted" not in body

    r2 = client.get("/api/ssh-targets")
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_anlegen_ohne_passwort_bei_passwort_auth_wird_abgelehnt(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel(password=None))
    assert r.status_code == 400


def test_anlegen_ohne_schluessel_bei_private_key_auth_wird_abgelehnt(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel(
        auth_method="private_key", password=None, private_key_pem=None,
    ))
    assert r.status_code == 400


def test_anlegen_mit_agent_braucht_kein_geheimnis(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel(auth_method="agent", password=None))
    assert r.status_code == 201


def test_anlegen_mit_ungueltiger_auth_method_wird_abgelehnt(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel(auth_method="unsinn"))
    assert r.status_code == 422


def test_anlegen_mit_leerem_namen_wird_abgelehnt(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel(name=""))
    assert r.status_code == 422


def test_anlegen_mit_ungueltigem_port_wird_abgelehnt(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel(port=70000))
    assert r.status_code == 422


def test_aktualisieren_ohne_geheimnis_aendert_nur_metadaten(client):
    ziel_id = client.post("/api/ssh-targets", json=_passwort_ziel()).json()["id"]

    r = client.put(f"/api/ssh-targets/{ziel_id}", json=_passwort_ziel(
        name="Umbenannt", password=None,
    ))
    assert r.status_code == 200
    assert r.json()["name"] == "Umbenannt"


def test_aktualisieren_auth_method_wechsel_ohne_neues_geheimnis_wird_abgelehnt(client):
    ziel_id = client.post("/api/ssh-targets", json=_passwort_ziel()).json()["id"]

    r = client.put(f"/api/ssh-targets/{ziel_id}", json=_passwort_ziel(
        auth_method="private_key", password=None, private_key_pem=None,
    ))
    assert r.status_code == 400


def test_aktualisieren_auth_method_wechsel_mit_neuem_geheimnis_klappt(client):
    ziel_id = client.post("/api/ssh-targets", json=_passwort_ziel()).json()["id"]

    r = client.put(f"/api/ssh-targets/{ziel_id}", json=_passwort_ziel(
        auth_method="private_key", password=None,
        private_key_pem="-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----",
    ))
    assert r.status_code == 200
    assert r.json()["auth_method"] == "private_key"


def test_aktualisieren_wechsel_zu_agent_braucht_kein_geheimnis(client):
    ziel_id = client.post("/api/ssh-targets", json=_passwort_ziel()).json()["id"]

    r = client.put(f"/api/ssh-targets/{ziel_id}", json=_passwort_ziel(
        auth_method="agent", password=None,
    ))
    assert r.status_code == 200
    assert r.json()["auth_method"] == "agent"


def test_loeschen(client):
    ziel_id = client.post("/api/ssh-targets", json=_passwort_ziel()).json()["id"]
    r = client.delete(f"/api/ssh-targets/{ziel_id}")
    assert r.status_code == 204
    assert client.get("/api/ssh-targets").json() == []


def test_verbindungstest_gegen_nicht_erreichbaren_host_liefert_fehlermeldung(client):
    # Port 1 auf localhost: kein SSH-Server dort, liefert sofort "connection
    # refused" statt eines langsamen Timeouts (anders als ein unerreichbares
    # Netz) - haelt den Test schnell.
    r = client.post("/api/ssh-targets/test", json=_passwort_ziel(host="127.0.0.1", port=1))
    assert r.status_code == 200
    body = r.json()
    assert body["erfolgreich"] is False
    assert body["meldung"]


def _direct_ziel(**overrides):
    daten = {
        "name": "Lokales Ollama",
        "host": "http://192.168.1.50:11434",
        "auth_method": "direct",
    }
    daten.update(overrides)
    return daten


def test_anlegen_direct_ziel_braucht_keinen_benutzernamen(client):
    r = client.post("/api/ssh-targets", json=_direct_ziel())
    assert r.status_code == 201
    assert r.json()["auth_method"] == "direct"


def test_anlegen_direct_ziel_ohne_http_praefix_wird_abgelehnt(client):
    r = client.post("/api/ssh-targets", json=_direct_ziel(host="192.168.1.50:11434"))
    assert r.status_code == 400


def test_anlegen_ssh_ziel_ohne_benutzernamen_wird_abgelehnt(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel(username=""))
    assert r.status_code == 400


def test_verbindungstest_direct_ziel_gegen_nicht_erreichbare_adresse(client):
    r = client.post("/api/ssh-targets/test", json=_direct_ziel(host="http://127.0.0.1:1"))
    assert r.status_code == 200
    body = r.json()
    assert body["erfolgreich"] is False
    assert body["meldung"]


def test_aktualisieren_wechsel_zu_direct_braucht_kein_geheimnis(client):
    ziel_id = client.post("/api/ssh-targets", json=_passwort_ziel()).json()["id"]

    r = client.put(f"/api/ssh-targets/{ziel_id}", json=_direct_ziel())
    assert r.status_code == 200
    assert r.json()["auth_method"] == "direct"


def test_favorit_ist_anfangs_false(client):
    r = client.post("/api/ssh-targets", json=_passwort_ziel())
    assert r.json()["favorit"] is False


def test_favorit_setzen(client):
    ziel_id = client.post("/api/ssh-targets", json=_passwort_ziel()).json()["id"]
    r = client.put(f"/api/ssh-targets/{ziel_id}/favorit", json={"favorit": True})
    assert r.status_code == 200
    assert r.json()["favorit"] is True


def test_favorit_ist_exklusiv(client):
    id1 = client.post("/api/ssh-targets", json=_passwort_ziel(name="Erstes")).json()["id"]
    id2 = client.post("/api/ssh-targets", json=_passwort_ziel(name="Zweites")).json()["id"]
    client.put(f"/api/ssh-targets/{id1}/favorit", json={"favorit": True})
    client.put(f"/api/ssh-targets/{id2}/favorit", json={"favorit": True})

    liste = client.get("/api/ssh-targets").json()
    favoriten = [z for z in liste if z["favorit"]]
    assert len(favoriten) == 1
    assert favoriten[0]["id"] == id2


def test_favorit_entfernen(client):
    ziel_id = client.post("/api/ssh-targets", json=_passwort_ziel()).json()["id"]
    client.put(f"/api/ssh-targets/{ziel_id}/favorit", json={"favorit": True})
    r = client.put(f"/api/ssh-targets/{ziel_id}/favorit", json={"favorit": False})
    assert r.status_code == 200
    assert r.json()["favorit"] is False


def test_favorit_setzen_fuer_unbekanntes_ziel_gibt_404(client):
    r = client.put("/api/ssh-targets/unbekannt/favorit", json={"favorit": True})
    assert r.status_code == 404
