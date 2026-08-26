import pytest
from fastapi.testclient import TestClient

from app.api import architekt as api_arch
from app.config import Settings, get_settings
from app.db import init_db
from app.main import app

"""Sichert zu, dass eine frisch ueber 'Epoche erstellen' angelegte (nicht
vorgefertigte) Epoche sofort alle drei Wege zu einem Story-Gerüst
unterstuetzt: gefuehrtes Interview, von Hand ausgefuellte Vorlage
(architekt-vorlage) und KI-Extraktion aus einem Handlungstext
(architekt-extraktion). Beide Vorlage-Wege haengen an derselben
STORY-GERUEST-Struktur, die app/core/epoche.py:architekt_vorlage() fuer
JEDE neue Epoche generiert (siehe app/core/architekt.py:_grundgeruest) -
dieser Test haelt das als Regression fest, statt es nur implizit ueber die
sechs mitgelieferten Epochen abzudecken."""


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


@pytest.fixture
def projekt(client):
    r = client.post("/api/epochen", json={
        "name": "Redrock-Territorium",
        "erfunden": True,
        "beschreibung": "einer erfundenen Wildwest-Welt namens Redrock-Territorium",
        "zeitraum": "Jahr X einer eigenen Zeitrechnung",
        "orte": "Saloon, Mine, Grenzstadt",
        "gesellschaft": "Gesetzlose Grenzregion, Kopfgeldjäger regieren.",
        "statusregel": "Ein gebrochenes Versprechen zieht Blutrache nach sich.",
    })
    assert r.status_code == 201

    r = client.post("/api/projects", json={"titel": "Testprojekt", "epoche": "Redrock-Territorium"})
    assert r.status_code == 201
    return r.json()["ordner"]


def test_architekt_vorlage_liefert_echtes_geruest_fuer_neu_angelegte_epoche(client, projekt):
    r = client.get(f"/api/projects/{projekt}/architekt-vorlage")
    assert r.status_code == 200
    vorlage = r.json()["vorlage"]
    assert "# STORY-GERUEST" in vorlage
    assert "## Kapitelplan" in vorlage
    assert "## Ausgangslage vor Kapitel eins" in vorlage
    assert "## Regeln" not in vorlage


def test_architekt_vorlage_figuren_abschnitt_verlangt_ueberschrift_statt_aufzaehlung(client, projekt):
    # Regression: "Je Figur: ... in einem Satz" hielt sich das Modell (Mistral)
    # bei reichhaltigen Fundus-Figuren nicht zuverlaessig dran und zerlegte
    # stattdessen jedes einzelne Merkmal in einen eigenen, gleichrangigen
    # Aufzaehlungspunkt neben dem Figurennamen - nicht mehr unterscheidbar,
    # welche Punkte Figurennamen und welche nur Feld-Bezeichner sind (Live-
    # Vorfall "Die-Schleier-zwischen-den-Welten": "Blutstatus"/"Rolle" sahen
    # strukturell identisch aus wie "Daniel Ertl"/"Luna Lovegood"). Die
    # Vorgabe verlangt jetzt explizit "### Name"-Ueberschriften statt Fliesstext.
    r = client.get(f"/api/projects/{projekt}/architekt-vorlage")
    assert r.status_code == 200
    vorlage = r.json()["vorlage"]
    assert "### Name der Figur" in vorlage
    assert "in einem Satz" not in vorlage


def test_architekt_extraktion_system_enthaelt_volle_struktur_fuer_neu_angelegte_epoche(client, projekt, monkeypatch):
    aufrufe = []

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        aufrufe.append(system)
        return "# STORY-GERUEST\n\n## Titel\nDer Kopfgeldjäger von Redrock\n", {}

    monkeypatch.setattr(api_arch, "sammle_antwort", fake_sammle_antwort)

    r = client.post(
        f"/api/projects/{projekt}/architekt-extraktion",
        json={"handlungstext": "Ein Kopfgeldjäger jagt einen Banditen durch die Grenzstadt Redrock."},
    )
    assert r.status_code == 200
    assert len(aufrufe) == 1
    assert "## Kapitelplan" in aufrufe[0]
    assert "## Ausgangslage vor Kapitel eins" in aufrufe[0]


def test_architekt_interview_persona_neu_angelegter_epoche_enthaelt_interview_regeln(client, projekt, tmp_path):
    personas_datei = tmp_path / "projects" / "daniel" / projekt / "personas" / "architekt.txt"
    persona_text = personas_datei.read_text(encoding="utf-8")
    assert "Stelle GENAU EINE Frage" in persona_text
    assert "# STORY-GERUEST" in persona_text
