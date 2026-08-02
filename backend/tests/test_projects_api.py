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


@pytest.fixture
def projekt(client):
    r = client.post("/api/projects", json={"titel": "Testprojekt", "epoche": "Regency"})
    assert r.status_code == 201
    return r.json()["ordner"]


def test_projektliste_zeigt_titel_und_kapitelanzahl_aus_projekt_unterordner(client, projekt, tmp_path):
    # Regression: die Listenansicht (GET /api/projects) suchte geruest.md
    # und kapitel_*.md faelschlich im AEUSSEREN Projektordner statt im
    # projekt/-Unterordner und zeigte deshalb immer Titel=None und
    # anzahl_kapitel=0, obwohl die Detailansicht (GET /api/projects/{ordner})
    # dieselben Dateien korrekt fand.
    antwort = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDer Turm im Nebel\n\n## Kapitelplan\n"
                   "Kapitel 1: Start. Zielwortzahl: 1000 Woerter.\n",
    })
    # Der abweichende Titel benennt den Ordner um (siehe
    # app/api/projects.py:geruest_schreiben) - fuer die weiteren Schritte
    # muss also der ZURUECKGEGEBENE neue Ordner verwendet werden, nicht mehr
    # der urspruengliche "projekt"-Fixture-Ordnername.
    aktueller_ordner = antwort.json()["neuer_ordner"] or projekt
    from app.core import projekt_dateien as pd
    projekt_pfad = tmp_path / "projects" / "daniel" / aktueller_ordner / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "Ein Kapiteltext.")

    r = client.get("/api/projects")
    assert r.status_code == 200
    eintrag = next(p for p in r.json() if p["ordner"] == aktueller_ordner)
    assert eintrag["titel"] == "Der Turm im Nebel"
    assert eintrag["anzahl_kapitel"] == 1
    assert eintrag["letztes_geplantes_kapitel"] == 1


def test_projektliste_zeigt_automatik_zustand_none_ohne_lauf(client, projekt):
    eintrag = next(p for p in client.get("/api/projects").json() if p["ordner"] == projekt)
    assert eintrag["automatik_zustand"] is None


def test_projektliste_zeigt_automatik_zustand_mit_resten(client, projekt, tmp_path):
    from app.core import automatik

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    status = automatik.status_lesen(projekt_root)
    status.update({
        "gestartet_am": "2026-01-01 12:00", "laeuft": False, "fehler": None,
        "abgeschlossen": True,
        "protokoll": [{"art": "uebersprungen", "grund": "konflikt"}],
    })
    automatik.status_schreiben(projekt_root, status)

    eintrag = next(p for p in client.get("/api/projects").json() if p["ordner"] == projekt)
    assert eintrag["automatik_zustand"] == "abgeschlossen_mit_resten"


def test_projekt_loeschen_entfernt_den_kompletten_ordner(client, projekt, tmp_path):
    projekt_root = tmp_path / "projects" / "daniel" / projekt
    assert projekt_root.is_dir()

    r = client.delete(f"/api/projects/{projekt}")

    assert r.status_code == 204
    assert not projekt_root.exists()
    assert client.get("/api/projects").json() == []


def test_projekt_loeschen_unbekannter_ordner_gibt_404(client):
    r = client.delete("/api/projects/nicht-vorhanden")
    assert r.status_code == 404


def test_projekt_loeschen_blockiert_waehrend_automatik_laeuft(client, projekt, tmp_path):
    from app.core import automatik

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    status = automatik.status_lesen(projekt_root)
    status["laeuft"] = True
    automatik.status_schreiben(projekt_root, status)

    r = client.delete(f"/api/projects/{projekt}")

    assert r.status_code == 409
    assert projekt_root.is_dir()


def test_verbotsliste_lesen_und_schreiben(client, projekt):
    r = client.get(f"/api/projects/{projekt}")
    assert r.status_code == 200
    assert "Verbotsliste" in r.json()["verbotsliste"]

    r2 = client.put(f"/api/projects/{projekt}/verbotsliste", json={"inhalt": "# Verbotsliste\n\nNeuer Eintrag"})
    assert r2.status_code == 200

    r3 = client.get(f"/api/projects/{projekt}")
    assert r3.json()["verbotsliste"] == "# Verbotsliste\n\nNeuer Eintrag"


def test_personas_auflisten(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas")
    assert r.status_code == 200
    namen = r.json()
    assert "architekt" in namen
    assert "autor" in namen
    assert "chronist" in namen


def test_persona_lesen_und_schreiben(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas/autor")
    assert r.status_code == 200
    assert len(r.text) > 0

    r2 = client.put(f"/api/projects/{projekt}/personas/autor", json={"inhalt": "Neue Autor-Persona"})
    assert r2.status_code == 200

    r3 = client.get(f"/api/projects/{projekt}/personas/autor")
    assert r3.text == "Neue Autor-Persona"


def test_persona_unbekannter_name_wird_abgelehnt(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas/nicht_vorhanden")
    assert r.status_code == 404

    r2 = client.put(f"/api/projects/{projekt}/personas/nicht_vorhanden", json={"inhalt": "x"})
    assert r2.status_code == 404


def test_architekten_gespraech_ohne_abgeschlossenes_interview_404(client, projekt):
    r = client.get(f"/api/projects/{projekt}/architekten-gespraech")
    assert r.status_code == 404


def test_projekt_anlegen_ohne_titel_verwendet_platzhalter_neu(client):
    r = client.post("/api/projects", json={"titel": "", "epoche": "Regency"})
    assert r.status_code == 201
    assert r.json()["ordner"] == "neu"
    assert r.json()["titel"] is None


def test_projekt_anlegen_ohne_titel_zaehlt_bei_kollision_hoch(client):
    r1 = client.post("/api/projects", json={"titel": "", "epoche": "Regency"})
    r2 = client.post("/api/projects", json={"titel": "", "epoche": "Regency"})
    assert r1.json()["ordner"] == "neu"
    assert r2.json()["ordner"] == "neu-2"


def test_projekt_anlegen_mit_epoche_unterordner(client, tmp_path):
    client.put("/api/einstellungen", json={"unterordner_je_epoche": True})
    r = client.post("/api/projects", json={"titel": "Der Sturm", "epoche": "Regency"})
    assert r.status_code == 201
    daten = r.json()
    assert daten["ordner"] == "Regency/Der-Sturm"
    assert (tmp_path / "projects" / "daniel" / "Regency" / "Der-Sturm" / "projekt").is_dir()

    r2 = client.get(f"/api/projects/{daten['ordner']}")
    assert r2.status_code == 200

    r3 = client.get("/api/projects")
    assert any(p["ordner"] == "Regency/Der-Sturm" for p in r3.json())


def test_projekt_mit_epoche_unterordner_geruest_lesen_und_schreiben(client):
    client.put("/api/einstellungen", json={"unterordner_je_epoche": True})
    ordner = client.post("/api/projects", json={"titel": "Der Sturm", "epoche": "Regency"}).json()["ordner"]

    r = client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDer Sturm\n",
    })
    assert r.status_code == 200

    r2 = client.get(f"/api/projects/{ordner}")
    assert "Der Sturm" in r2.json()["geruest"]


def test_projekt_anlegen_mit_zweiter_epoche_setzt_zeitsprung_marker(client, tmp_path):
    r = client.post("/api/projects", json={
        "titel": "Der Sprung durch die Zeit", "epoche": "Mittelalter", "zweite_epoche": "Zukunft",
    })
    assert r.status_code == 201
    daten = r.json()
    assert daten["epoche"] == "Mittelalter"
    assert daten["zweite_epoche"] == "Zukunft"

    r2 = client.get(f"/api/projects/{daten['ordner']}")
    assert r2.json()["epoche"] == "Mittelalter"
    assert r2.json()["zweite_epoche"] == "Zukunft"

    personas = tmp_path / "projects" / "daniel" / daten["ordner"] / "personas"
    for datei in ("architekt.txt", "autor.txt", "pruefer_anachronismus.txt"):
        inhalt = (personas / datei).read_text(encoding="utf-8")
        assert "ZEITSPRUNG" in inhalt
        assert "Zukunft" in inhalt

    verbotsliste = (tmp_path / "projects" / "daniel" / daten["ordner"] / "projekt" / "verbotsliste.md").read_text(
        encoding="utf-8",
    )
    assert "Epoche: Mittelalter" in verbotsliste
    assert "Epoche: Zukunft" in verbotsliste


def test_projekt_anlegen_ohne_zweite_epoche_hat_keinen_zeitsprung_marker(client, projekt, tmp_path):
    assert not (tmp_path / "projects" / "daniel" / projekt / ".epoche_zweite").exists()
    r = client.get(f"/api/projects/{projekt}")
    assert r.json()["zweite_epoche"] is None


def test_projekt_anlegen_mit_gleicher_zweiter_epoche_wird_abgelehnt(client):
    r = client.post("/api/projects", json={
        "titel": "X", "epoche": "Regency", "zweite_epoche": "Regency",
    })
    assert r.status_code == 422


def test_projekt_anlegen_mit_unbekannter_zweiter_epoche_gibt_404(client):
    r = client.post("/api/projects", json={
        "titel": "X", "epoche": "Regency", "zweite_epoche": "Nicht-Vorhanden",
    })
    assert r.status_code == 404


def test_projekt_ohne_epoche_unterordner_bleibt_flach(client, tmp_path):
    r = client.post("/api/projects", json={"titel": "Der Sturm", "epoche": "Regency"})
    assert r.json()["ordner"] == "Der-Sturm"
    assert (tmp_path / "projects" / "daniel" / "Der-Sturm" / "projekt").is_dir()
