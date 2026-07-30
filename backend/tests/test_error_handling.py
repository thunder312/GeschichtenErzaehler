"""Reproduziert den gemeldeten Bug: ein REST-Endpunkt, der Ollama nicht
erreicht (z.B. weil kein SSH-Ziel ausgewaehlt wurde und kein lokales Ollama
laeuft), lieferte vorher ein nacktes 500 Internal Server Error statt einer
verwertbaren Fehlermeldung. Gleiches fuer eine fehlende Kapiteldatei."""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.api.pipeline import _hunspell_exec_fn
from app.config import Settings, get_settings
from app.core import projekt_dateien as pd
from app.db import init_db
from app.main import app


@pytest.fixture
def settings(tmp_path):
    s = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        ollama_url="http://127.0.0.1:1",  # garantiert nicht erreichbar, kein Timeout-Risiko
    )
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(s.database_path)
    return s


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def projekt_mit_kapitel(client, tmp_path):
    r = client.post("/api/projects", json={"titel": "Fehlertest", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={"inhalt": "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\n"})
    projekt_pfad = tmp_path / "projects" / "daniel" / ordner / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "Ein Testkapitel.")
    return ordner


def test_pruefen_ohne_erreichbares_ollama_liefert_502_statt_500(client, projekt_mit_kapitel):
    r = client.post(f"/api/projects/{projekt_mit_kapitel}/pruefen/1")
    assert r.status_code == 502
    assert "detail" in r.json()
    assert r.json()["detail"]


def test_pruefen_fuer_nicht_geschriebenes_kapitel_liefert_404_statt_500(client, projekt_mit_kapitel):
    r = client.post(f"/api/projects/{projekt_mit_kapitel}/pruefen/99")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_hunspell_exec_fn_liefert_none_fuer_direct_ziel_statt_ssh_absturz(settings):
    """Regression: ein 'direct'-KI-Ziel (auth_method='direct', host=komplette
    HTTP-Basis-URL wie 'http://127.0.0.1:18321') hat keine echte SSH-
    Verbindung. _hunspell_exec_fn versuchte trotzdem, per ssh_manager exec zu
    verbinden, und krachte mit einer nicht abgefangenen SSHVerbindungsFehler
    quer durch den WebSocket-Handler (live auf dem Deploy beobachtet, direkt
    nachdem ein Kapitel ueber den Reverse-Tunnel geschrieben wurde) - die
    Verbindung riss ab, ohne dass das Frontend je eine 'abgeschlossen'- oder
    Fehler-Nachricht bekam, obwohl das Kapitel bereits gespeichert war."""
    ziel_id = db.ssh_ziel_anlegen(
        settings.database_path, settings.secret_key_path,
        name="Direkt-Ziel", host="http://127.0.0.1:18321",
        port=22, username="", auth_method="direct",
        geheimnis={}, remote_ollama_port=11434,
    )

    exec_fn = _hunspell_exec_fn(settings, ziel_id)

    assert exec_fn is None


def test_rechtschreibung_mit_direct_ziel_liefert_hunspell_nicht_verfuegbar_statt_500(client, settings, projekt_mit_kapitel):
    ziel_id = db.ssh_ziel_anlegen(
        settings.database_path, settings.secret_key_path,
        name="Direkt-Ziel", host="http://127.0.0.1:18321",
        port=22, username="", auth_method="direct",
        geheimnis={}, remote_ollama_port=11434,
    )

    r = client.get(f"/api/projects/{projekt_mit_kapitel}/rechtschreibung/1?ssh_ziel_id={ziel_id}")

    assert r.status_code == 200
    assert r.json()["hunspell_verfuegbar"] is False
