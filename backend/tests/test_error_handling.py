"""Reproduziert den gemeldeten Bug: ein REST-Endpunkt, der Ollama nicht
erreicht (z.B. weil kein SSH-Ziel ausgewaehlt wurde und kein lokales Ollama
laeuft), lieferte vorher ein nacktes 500 Internal Server Error statt einer
verwertbaren Fehlermeldung. Gleiches fuer eine fehlende Kapiteldatei."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core import projekt_dateien as pd
from app.db import init_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        ollama_url="http://127.0.0.1:1",  # garantiert nicht erreichbar, kein Timeout-Risiko
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def projekt_mit_kapitel(client, tmp_path):
    r = client.post("/api/projects", json={"titel": "Fehlertest", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={"inhalt": "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\n"})
    projekt_pfad = tmp_path / "projects" / ordner / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "Ein Testkapitel.")
    return ordner


def test_pruefen_ohne_erreichbares_ollama_liefert_502_statt_500(client, projekt_mit_kapitel):
    r = client.post(f"/api/projects/{projekt_mit_kapitel}/pruefen/1")
    assert r.status_code == 502
    assert "detail" in r.json()
    assert r.json()["detail"]


def test_lektorieren_ohne_erreichbares_ollama_liefert_502(client, projekt_mit_kapitel):
    r = client.post(f"/api/projects/{projekt_mit_kapitel}/lektorieren/1")
    assert r.status_code == 502


def test_pruefen_fuer_nicht_geschriebenes_kapitel_liefert_404_statt_500(client, projekt_mit_kapitel):
    r = client.post(f"/api/projects/{projekt_mit_kapitel}/pruefen/99")
    assert r.status_code == 404
    assert "detail" in r.json()
