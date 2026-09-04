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


def test_orte_lesen_liefert_leere_vorlage_wenn_datei_fehlt(client):
    r = client.get("/api/orte")
    assert r.status_code == 200
    assert "ORTE-VORLAGE" in r.text


def test_orte_schreiben_und_lesen_roundtrip(client):
    inhalt = "<!-- Kopf -->\n\n## Regency\n\n### Marktplatz\n- Beschreibung: Belebt.\n"
    r = client.put("/api/orte", json={"inhalt": inhalt})
    assert r.status_code == 200

    r = client.get("/api/orte")
    assert r.status_code == 200
    assert "Marktplatz" in r.text


def test_ort_anlegen_lesen_und_duplikat_ablehnen(client):
    r = client.post("/api/orte/orte", json={
        "epoche": "Regency", "name": "Marktplatz von Rothenfeld", "beschreibung": "Belebter Platz.",
    })
    assert r.status_code == 201
    assert r.json() == {"epoche": "Regency", "name": "Marktplatz von Rothenfeld", "beschreibung": "Belebter Platz."}

    r = client.get("/api/orte/orte")
    assert r.status_code == 200
    assert r.json()["orte"] == [
        {"epoche": "Regency", "name": "Marktplatz von Rothenfeld", "beschreibung": "Belebter Platz."},
    ]

    r = client.post("/api/orte/orte", json={
        "epoche": "Regency", "name": "marktplatz von rothenfeld", "beschreibung": "Anderer Text.",
    })
    assert r.status_code == 409


def test_ort_anlegen_lehnt_leeren_namen_ab(client):
    r = client.post("/api/orte/orte", json={"epoche": "Regency", "name": "  ", "beschreibung": ""})
    assert r.status_code == 400


def test_ort_aktualisieren_beschreibung_und_umbenennen(client):
    client.post("/api/orte/orte", json={"epoche": "Regency", "name": "Marktplatz", "beschreibung": "Alt."})

    r = client.put("/api/orte/orte", json={
        "epoche": "Regency", "name": "Marktplatz",
        "neuer_name": "Großer Marktplatz", "beschreibung": "Neu beschrieben.",
    })
    assert r.status_code == 200
    assert r.json() == {"epoche": "Regency", "name": "Großer Marktplatz", "beschreibung": "Neu beschrieben."}

    orte = client.get("/api/orte/orte").json()["orte"]
    assert len(orte) == 1
    assert orte[0]["name"] == "Großer Marktplatz"


def test_ort_aktualisieren_verschiebt_in_andere_epoche(client):
    client.post("/api/orte/orte", json={"epoche": "Regency", "name": "Marktplatz", "beschreibung": "X"})

    r = client.put("/api/orte/orte", json={
        "epoche": "Regency", "name": "Marktplatz", "neue_epoche": "Mittelalter", "beschreibung": "X",
    })
    assert r.status_code == 200
    assert r.json()["epoche"] == "Mittelalter"


def test_ort_aktualisieren_lehnt_kollision_im_ziel_ab(client):
    client.post("/api/orte/orte", json={"epoche": "Regency", "name": "Marktplatz", "beschreibung": "X"})
    client.post("/api/orte/orte", json={"epoche": "Mittelalter", "name": "Marktplatz", "beschreibung": "Y"})

    r = client.put("/api/orte/orte", json={
        "epoche": "Regency", "name": "Marktplatz", "neue_epoche": "Mittelalter", "beschreibung": "X",
    })
    assert r.status_code == 409


def test_ort_aktualisieren_unbekannter_ort_liefert_404(client):
    r = client.put("/api/orte/orte", json={"epoche": "Regency", "name": "Unbekannt", "beschreibung": "X"})
    assert r.status_code == 404


def test_ort_loeschen(client):
    client.post("/api/orte/orte", json={"epoche": "Regency", "name": "Marktplatz", "beschreibung": "X"})

    r = client.delete("/api/orte/orte", params={"epoche": "Regency", "name": "Marktplatz"})
    assert r.status_code == 200
    assert r.json() == {"gelöscht": True}
    assert client.get("/api/orte/orte").json()["orte"] == []


def test_ort_loeschen_unbekannter_ort_liefert_404(client):
    r = client.delete("/api/orte/orte", params={"epoche": "Regency", "name": "Unbekannt"})
    assert r.status_code == 404
