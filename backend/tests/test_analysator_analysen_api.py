import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core import analysator as an
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


def test_analysen_auflisten_ist_leer_ohne_gespeicherte_analysen(client):
    r = client.get("/api/analysator/analysen")
    assert r.status_code == 200
    assert r.json() == []


def test_analysen_auflisten_zeigt_gespeicherte_analyse(client, tmp_path):
    an.analyse_speichern(tmp_path / "projects" / "daniel", "Meine Geschichte", "Ein langer Rohtext mit Woertern.")

    r = client.get("/api/analysator/analysen")
    assert r.status_code == 200
    liste = r.json()
    assert len(liste) == 1
    assert liste[0]["dateiname"] == "Meine-Geschichte.md"
    assert liste[0]["titel"] == "Meine Geschichte"
    assert liste[0]["woerter"] == 5


def test_analysen_auflisten_sortiert_neueste_zuerst(client, tmp_path):
    wurzel = tmp_path / "projects" / "daniel"
    an.analyse_speichern(wurzel, "Aelter", "x")
    # Echte, kleine Verzoegerung noetig, nicht os.utime()-Backdating: Windows
    # setzt die Erstellungszeit (st_ctime) einer Datei nicht ueber os.utime()
    # zurueck (anders als mtime/atime) - ohne eine tatsaechliche Zeitluecke
    # koennten beide Dateien dieselbe Sekunde treffen und der Sortier-
    # Schluessel waere nicht mehr eindeutig unterscheidbar.
    import time
    time.sleep(1.1)
    an.analyse_speichern(wurzel, "Neuer", "y")

    r = client.get("/api/analysator/analysen")
    titel = [e["titel"] for e in r.json()]
    assert titel[0] == "Neuer"
    assert titel[1] == "Aelter"


def test_analyse_lesen_liefert_rohtext(client, tmp_path):
    an.analyse_speichern(tmp_path / "projects" / "daniel", "Titel", "Der gespeicherte Rohtext.")

    r = client.get("/api/analysator/analysen/Titel.md")
    assert r.status_code == 200
    assert r.text == "Der gespeicherte Rohtext."


def test_analyse_lesen_unbekannte_datei_gibt_404(client):
    r = client.get("/api/analysator/analysen/nicht-vorhanden.md")
    assert r.status_code == 404


def test_analyse_lesen_verhindert_path_traversal(client):
    r = client.get("/api/analysator/analysen/..%2F..%2Fnovelle_gui.db")
    assert r.status_code in (400, 404)


def test_analyse_loeschen_entfernt_datei(client, tmp_path):
    an.analyse_speichern(tmp_path / "projects" / "daniel", "Titel", "Text")
    ziel = tmp_path / "projects" / "daniel" / "Analyse" / "Titel.md"
    assert ziel.exists()

    r = client.delete("/api/analysator/analysen/Titel.md")
    assert r.status_code == 204
    assert not ziel.exists()

    liste = client.get("/api/analysator/analysen").json()
    assert liste == []


def test_analyse_loeschen_unbekannte_datei_gibt_404(client):
    r = client.delete("/api/analysator/analysen/nicht-vorhanden.md")
    assert r.status_code == 404


# --- Quelldatei des Rohtexts (Format der Uebersetzung, z.B. PDF) ---------------------

def test_quelldatei_wird_gespeichert_und_aufgelistet(client, tmp_path):
    wurzel = tmp_path / "projects" / "daniel"
    an.analyse_speichern(wurzel, "Mit Quelle", "Ein Text.", quelldatei="Buch_Original.pdf")
    an.analyse_speichern(wurzel, "Ohne Quelle", "Anderer Text.")

    liste = {e["titel"]: e for e in client.get("/api/analysator/analysen").json()}
    assert liste["Mit Quelle"]["quelldatei"] == "Buch_Original.pdf"
    assert liste["Ohne Quelle"]["quelldatei"] is None  # aeltere Eintraege ohne Vermerk
    # Die Meta-Datei taucht NICHT als eigener Rohtext in der Liste auf
    assert len(liste) == 2


def test_quelldatei_nimmt_nur_den_dateinamen_ohne_pfad(client, tmp_path):
    wurzel = tmp_path / "projects" / "daniel"
    an.analyse_speichern(wurzel, "Pfad", "x", quelldatei="C:\\Users\\jemand\\Buecher\\Roman.pdf")
    an.analyse_speichern(wurzel, "Pfad2", "x", quelldatei="../../etc/passwd")
    liste = {e["titel"]: e["quelldatei"] for e in client.get("/api/analysator/analysen").json()}
    assert liste["Pfad"] in ("Roman.pdf", "C:\\Users\\jemand\\Buecher\\Roman.pdf".replace("\\", "/").split("/")[-1])
    assert "/" not in liste["Pfad2"] and ".." not in liste["Pfad2"]


def test_analyse_loeschen_entfernt_auch_die_meta_datei(client, tmp_path):
    wurzel = tmp_path / "projects" / "daniel"
    an.analyse_speichern(wurzel, "Titel", "Text", quelldatei="X.pdf")
    meta = wurzel / "Analyse" / "Titel.meta.json"
    assert meta.exists()
    assert client.delete("/api/analysator/analysen/Titel.md").status_code == 204
    assert not meta.exists()


def test_start_speichert_die_quelldatei_beim_rohtext(client, tmp_path, monkeypatch):
    import app.api.analysator as analysator_api

    async def nichts(*args, **kwargs):
        return None

    monkeypatch.setattr(analysator_api, "_analysieren_lauf", nichts)
    settings = app.dependency_overrides[get_settings]()
    (settings.epochen_dir / "Regency").mkdir(parents=True, exist_ok=True)
    for datei in ("architekt.txt", "autor.txt", "pruefer_anachronismus.txt"):
        (settings.epochen_dir / "Regency" / datei).write_text("x", encoding="utf-8")
    r = client.post("/api/analysator/starten", json={
        "titel": "Mein Import", "epoche": "Regency", "text": "Ein importierter Text.", "quelldatei": "Quelle.pdf",
    })
    assert r.status_code == 201
    liste = client.get("/api/analysator/analysen").json()
    assert [e["quelldatei"] for e in liste] == ["Quelle.pdf"]
