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


def test_epoche_erstellen_legt_fuenf_dateien_an(client, tmp_path):
    r = client.post("/api/epochen", json=_reale_epoche())
    assert r.status_code == 201
    body = r.json()
    assert body["ordner"] == "Viktorianisches-England"
    assert set(body["dateien"].keys()) == {
        "architekt.txt", "autor.txt", "pruefer_anachronismus.txt", "verbotsliste.md", "einleitungssatz.txt",
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
    assert "Genre-Prägung: Krimi." in r.json()["dateien"]["architekt.txt"]
    assert (tmp_path / "epochen" / "Viktorianisches-England" / ".genre").read_text(encoding="utf-8") == "Krimi"

    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Viktorianisches-England")
    assert eintrag["genre"] == "Krimi"


def test_epoche_erstellen_ohne_genre_hat_kein_genre_in_liste(client):
    client.post("/api/epochen", json=_reale_epoche())
    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Viktorianisches-England")
    assert eintrag["genre"] is None


def test_epoche_loeschen_entfernt_ordner_aus_bibliothek(client, tmp_path):
    client.post("/api/epochen", json=_reale_epoche())
    ziel = tmp_path / "epochen" / "Viktorianisches-England"
    assert ziel.is_dir()

    r = client.delete("/api/epochen/Viktorianisches-England")
    assert r.status_code == 204
    assert not ziel.exists()

    liste = client.get("/api/projects/epochen").json()
    assert not any(e["name"] == "Viktorianisches-England" for e in liste)


def test_epoche_loeschen_unbekannter_ordner_gibt_404(client):
    r = client.delete("/api/epochen/Nicht-Vorhanden")
    assert r.status_code == 404


def test_epoche_dateien_auflisten_liefert_alle_fuenf(client):
    client.post("/api/epochen", json=_reale_epoche())
    r = client.get("/api/epochen/Viktorianisches-England/dateien")
    assert r.status_code == 200
    assert set(r.json()) == {
        "architekt.txt", "autor.txt", "pruefer_anachronismus.txt", "verbotsliste.md", "einleitungssatz.txt",
    }


def test_epoche_dateien_auflisten_unbekannte_epoche_gibt_404(client):
    r = client.get("/api/epochen/Nicht-Vorhanden/dateien")
    assert r.status_code == 404


def test_epoche_datei_lesen_liefert_inhalt(client):
    angelegt = client.post("/api/epochen", json=_reale_epoche()).json()
    r = client.get("/api/epochen/Viktorianisches-England/dateien/autor.txt")
    assert r.status_code == 200
    assert r.text == angelegt["dateien"]["autor.txt"]


def test_epoche_datei_lesen_unbekannter_dateiname_gibt_404(client):
    client.post("/api/epochen", json=_reale_epoche())
    r = client.get("/api/epochen/Viktorianisches-England/dateien/nicht_erlaubt.txt")
    assert r.status_code == 404


def test_epoche_datei_schreiben_persistiert_aenderung(client, tmp_path):
    client.post("/api/epochen", json=_reale_epoche())
    r = client.put(
        "/api/epochen/Viktorianisches-England/dateien/verbotsliste.md",
        json={"inhalt": "- Nachbearbeitete Verbotsliste"},
    )
    assert r.status_code == 200

    ziel = tmp_path / "epochen" / "Viktorianisches-England" / "verbotsliste.md"
    assert ziel.read_text(encoding="utf-8") == "- Nachbearbeitete Verbotsliste"

    gelesen = client.get("/api/epochen/Viktorianisches-England/dateien/verbotsliste.md")
    assert gelesen.text == "- Nachbearbeitete Verbotsliste"


def test_epoche_datei_schreiben_unbekannte_epoche_gibt_404(client):
    r = client.put("/api/epochen/Nicht-Vorhanden/dateien/autor.txt", json={"inhalt": "x"})
    assert r.status_code == 404


def test_epoche_datei_schreiben_wirkt_sich_nicht_auf_bereits_angelegtes_projekt_aus(client, tmp_path):
    """Bestaetigt dieselbe Entkopplung wie bei epoche_loeschen(): ein
    Projekt haelt eine eigene Kopie der Persona-Datei, die von einer
    spaeteren Bearbeitung der zentralen Epoche unberuehrt bleibt."""
    client.post("/api/epochen", json=_reale_epoche())
    projekt = client.post(
        "/api/projects", json={"titel": "Testgeschichte", "epoche": "Viktorianisches-England"},
    ).json()
    projekt_autor_vorher = (tmp_path / "projects" / "daniel" / projekt["ordner"] / "personas" / "autor.txt").read_text(
        encoding="utf-8",
    )

    client.put("/api/epochen/Viktorianisches-England/dateien/autor.txt", json={"inhalt": "Komplett neuer Autor-Text"})

    projekt_autor_nachher = (tmp_path / "projects" / "daniel" / projekt["ordner"] / "personas" / "autor.txt").read_text(
        encoding="utf-8",
    )
    assert projekt_autor_nachher == projekt_autor_vorher
    assert projekt_autor_nachher != "Komplett neuer Autor-Text"


def test_epoche_genre_schreiben_setzt_und_ueberschreibt(client):
    client.post("/api/epochen", json=_reale_epoche())
    r = client.put("/api/epochen/Viktorianisches-England/genre", json={"genre": "Krimi"})
    assert r.status_code == 200
    assert r.json()["genre"] == "Krimi"

    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Viktorianisches-England")
    assert eintrag["genre"] == "Krimi"

    r2 = client.put("/api/epochen/Viktorianisches-England/genre", json={"genre": "Dark Fantasy"})
    assert r2.json()["genre"] == "Dark Fantasy"


def test_epoche_genre_schreiben_mit_leerem_wert_entfernt_marker(client, tmp_path):
    client.post("/api/epochen", json=_reale_epoche(genre="Krimi"))
    marker = tmp_path / "epochen" / "Viktorianisches-England" / ".genre"
    assert marker.exists()

    r = client.put("/api/epochen/Viktorianisches-England/genre", json={"genre": ""})
    assert r.json()["genre"] is None
    assert not marker.exists()


def test_epoche_farbe_schreiben_setzt_und_ueberschreibt(client):
    client.post("/api/epochen", json=_reale_epoche())
    r = client.put("/api/epochen/Viktorianisches-England/farbe", json={"farbe": "#a16207"})
    assert r.status_code == 200
    assert r.json()["farbe"] == "#a16207"

    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Viktorianisches-England")
    assert eintrag["farbe"] == "#a16207"

    r2 = client.put("/api/epochen/Viktorianisches-England/farbe", json={"farbe": "#2563eb"})
    assert r2.json()["farbe"] == "#2563eb"


def test_epoche_farbe_schreiben_mit_leerem_wert_entfernt_marker(client, tmp_path):
    client.post("/api/epochen", json=_reale_epoche())
    client.put("/api/epochen/Viktorianisches-England/farbe", json={"farbe": "#a16207"})
    marker = tmp_path / "epochen" / "Viktorianisches-England" / ".farbe"
    assert marker.exists()

    r = client.put("/api/epochen/Viktorianisches-England/farbe", json={"farbe": ""})
    assert r.json()["farbe"] is None
    assert not marker.exists()


def test_epoche_ohne_farbe_hat_keine_farbe_in_liste(client):
    client.post("/api/epochen", json=_reale_epoche())
    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Viktorianisches-England")
    assert eintrag["farbe"] is None


def test_epoche_erstellen_setzt_anzeigename_gleich_dem_getippten_namen(client):
    client.post("/api/epochen", json=_reale_epoche())
    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Viktorianisches-England")
    assert eintrag["anzeigename"] == "Viktorianisches England"


def test_epoche_ohne_name_marker_hat_bindestriche_als_leerzeichen_im_anzeigenamen(client, tmp_path):
    # Epochen aus der Zeit vor dem ".name"-Marker (siehe
    # app/api/projects.py:_epoche_anzeigename_lesen) - Ersatzstrategie statt
    # eines echten Anzeigenamens.
    (tmp_path / "epochen" / "Jetzt-2026").mkdir(parents=True)
    liste = client.get("/api/projects/epochen").json()
    eintrag = next(e for e in liste if e["name"] == "Jetzt-2026")
    assert eintrag["anzeigename"] == "Jetzt 2026"


def test_epoche_umbenennen_aendert_nur_anzeigename_wenn_ordnername_gleich_bleibt(client, tmp_path):
    client.post("/api/epochen", json=_reale_epoche(name="Mittelalter"))
    r = client.put("/api/epochen/Mittelalter/name", json={"name": "Mittelalter"})
    assert r.status_code == 200
    body = r.json()
    assert body["ordner"] == "Mittelalter"
    assert body["anzeigename"] == "Mittelalter"
    assert body["aktualisierte_projekte"] == 0
    assert (tmp_path / "epochen" / "Mittelalter").is_dir()


def test_epoche_umbenennen_verschiebt_ordner_und_behaelt_leerzeichen(client, tmp_path):
    client.post("/api/epochen", json=_reale_epoche())
    r = client.put("/api/epochen/Viktorianisches-England/name", json={"name": "Viktorianisches England (spät)"})
    assert r.status_code == 200
    body = r.json()
    assert body["ordner"] == "Viktorianisches England (spät)"
    assert body["anzeigename"] == "Viktorianisches England (spät)"

    assert not (tmp_path / "epochen" / "Viktorianisches-England").exists()
    neuer_pfad = tmp_path / "epochen" / "Viktorianisches England (spät)"
    assert neuer_pfad.is_dir()
    assert (neuer_pfad / ".name").read_text(encoding="utf-8") == "Viktorianisches England (spät)"

    liste = client.get("/api/projects/epochen").json()
    assert any(e["name"] == "Viktorianisches England (spät)" for e in liste)
    assert not any(e["name"] == "Viktorianisches-England" for e in liste)


def test_epoche_umbenennen_zieht_bestehende_projekte_nach(client, tmp_path):
    client.post("/api/epochen", json=_reale_epoche())
    projekt = client.post(
        "/api/projects", json={"titel": "Testgeschichte", "epoche": "Viktorianisches-England"},
    ).json()["ordner"]

    r = client.put("/api/epochen/Viktorianisches-England/name", json={"name": "Viktorianisches England (spät)"})
    assert r.status_code == 200
    assert r.json()["aktualisierte_projekte"] == 1

    marker = tmp_path / "projects" / "daniel" / projekt / ".epoche"
    assert marker.read_text(encoding="utf-8") == "Viktorianisches England (spät)"

    liste = client.get("/api/projects").json()
    eintrag = next(p for p in liste if p["ordner"] == projekt)
    assert eintrag["epoche"] == "Viktorianisches England (spät)"


def test_epoche_umbenennen_zieht_unterordner_je_epoche_gruppenordner_nach(client, tmp_path):
    from app import db

    settings = client.app.dependency_overrides[get_settings]()
    db.einstellung_unterordner_je_epoche_schreiben(settings.database_path, True)

    client.post("/api/epochen", json=_reale_epoche())
    projekt = client.post(
        "/api/projects", json={"titel": "Testgeschichte", "epoche": "Viktorianisches-England"},
    ).json()["ordner"]
    assert projekt == "Viktorianisches-England/Testgeschichte"

    client.put("/api/epochen/Viktorianisches-England/name", json={"name": "Viktorianisches England (spät)"})

    alter_gruppenordner = tmp_path / "projects" / "daniel" / "Viktorianisches-England"
    neuer_gruppenordner = tmp_path / "projects" / "daniel" / "Viktorianisches England (spät)"
    assert not alter_gruppenordner.exists()
    assert (neuer_gruppenordner / "Testgeschichte").is_dir()


def test_epoche_umbenennen_konflikt_bei_bereits_existierendem_zielordner(client, tmp_path):
    client.post("/api/epochen", json=_reale_epoche())
    # Direkt als Ordner angelegt (nicht ueber /api/epochen, das fuer den
    # Ordnernamen die ASCII-Kurzform ordnername_aus_titel() verwendet,
    # waehrend das Umbenennen unten ordner_lesbarer_name() mit echten
    # Leerzeichen nutzt - fuer einen garantierten Namenskonflikt muss das
    # Zielverzeichnis exakt so heissen, wie epoche_umbenennen() es berechnet).
    (tmp_path / "epochen" / "Belle Epoque").mkdir()
    r = client.put("/api/epochen/Viktorianisches-England/name", json={"name": "Belle Epoque"})
    assert r.status_code == 409


def test_epoche_umbenennen_leerer_name_wird_abgelehnt(client):
    client.post("/api/epochen", json=_reale_epoche())
    r = client.put("/api/epochen/Viktorianisches-England/name", json={"name": "   "})
    assert r.status_code == 422


def test_epoche_umbenennen_unbekannte_epoche_gibt_404(client):
    r = client.put("/api/epochen/Nicht-Vorhanden/name", json={"name": "Neuer Name"})
    assert r.status_code == 404
