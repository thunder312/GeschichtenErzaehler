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
        epochen_dir=tmp_path / "epochen",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    settings.epochen_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _reale_epoche(**overrides):
    daten = {
        "name": "Viktorianisches England",
        "erfunden": False,
        "beschreibung": "dem viktorianischen England, ca. 1837 bis 1901",
        "zeitraum": "Jahr innerhalb 1837 bis 1901",
        "orte": "Landhaus, London, Kueste",
        "gesellschaft": "Strenge Etikette, Standesdenken.",
        "statusregel": "Eine unstandesgemaesse Heirat ruiniert die Familie gesellschaftlich.",
    }
    daten.update(overrides)
    return daten


def test_epoche_erstellen_legt_vier_dateien_an(client, tmp_path):
    r = client.post("/api/epochen", json=_reale_epoche())
    assert r.status_code == 201
    body = r.json()
    assert body["ordner"] == "Viktorianisches-England"
    assert set(body["dateien"].keys()) == {
        "architekt.txt", "autor.txt", "pruefer_anachronismus.txt", "verbotsliste.md",
    }

    ziel = tmp_path / "epochen" / "Viktorianisches-England"
    for name in body["dateien"]:
        assert (ziel / name).exists()


def test_epoche_erstellen_konflikt_bei_existierendem_ordner(client):
    client.post("/api/epochen", json=_reale_epoche())
    r = client.post("/api/epochen", json=_reale_epoche())
    assert r.status_code == 409


def test_epoche_erstellen_reale_epoche_hat_historischen_pruefer(client):
    r = client.post("/api/epochen", json=_reale_epoche())
    pruefer = r.json()["dateien"]["pruefer_anachronismus.txt"]
    assert "Anachronismen" in pruefer
    assert "Welt-Konsistenz" not in pruefer


def test_epoche_erstellen_erfunden_hat_welt_konsistenz_pruefer(client):
    r = client.post("/api/epochen", json=_reale_epoche(
        name="Redrock-Territorium",
        erfunden=True,
        beschreibung="einer erfundenen Wildwest-Welt namens Redrock-Territorium",
        zeitraum="Jahr X einer eigenen Zeitrechnung",
        vorbild_franchise="Red Dead Redemption",
    ))
    assert r.status_code == 201
    dateien = r.json()["dateien"]
    pruefer = dateien["pruefer_anachronismus.txt"]
    assert "Welt-Konsistenz" in pruefer
    assert "Markenabstand: Red Dead Redemption" in dateien["autor.txt"]


def test_epoche_erstellen_defaults_fuer_optionale_felder(client):
    r = client.post("/api/epochen", json=_reale_epoche())
    architekt_text = r.json()["dateien"]["architekt.txt"]
    assert "Name, Stand, Rolle" in architekt_text


def test_epoche_erstellen_verbotsliste_uebernimmt_kommagetrennte_eintraege(client):
    r = client.post("/api/epochen", json=_reale_epoche(
        verbote_start="Eisenbahn, Fotografie, moderne Anglizismen",
    ))
    verbotsliste = r.json()["dateien"]["verbotsliste.md"]
    assert "- Eisenbahn" in verbotsliste
    assert "- Fotografie" in verbotsliste
    assert "- moderne Anglizismen" in verbotsliste


def test_epoche_erstellen_mit_leerem_namen_wird_abgelehnt(client):
    r = client.post("/api/epochen", json=_reale_epoche(name=""))
    assert r.status_code == 422


def test_epoche_erstellen_mit_genre_wird_in_vorlagen_und_liste_uebernommen(client, tmp_path):
    r = client.post("/api/epochen", json=_reale_epoche(genre="Krimi"))
    assert r.status_code == 201
    assert "Genre-Praegung: Krimi." in r.json()["dateien"]["architekt.txt"]
    assert (tmp_path / "epochen" / "Viktorianisches-England" / ".genre").read_text(encoding="utf-8") == "Krimi"

    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Viktorianisches-England")
    assert eintrag["genre"] == "Krimi"


def test_epoche_erstellen_ohne_genre_hat_kein_genre_in_liste(client):
    client.post("/api/epochen", json=_reale_epoche())
    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Viktorianisches-England")
    assert eintrag["genre"] is None
