"""Ablauf "KI starten & Modelle scannen" (app/core/ki_start.py) und sein
API-Endpunkt - ohne Docker/Ollama, alles mit Attrappen."""
import time

import pytest
from fastapi.testclient import TestClient

from app.api import ssh_targets
from app.config import Settings, get_settings
from app.core import ki_start
from app.core.ki_start import KiStartHilfen, ki_starten
from app.db import init_db
from app.main import app

MODELLE = [{"name": "gemma4:latest", "parameter_size": "7.5B", "size_bytes": 1}]


class Welt:
    """Mini-Simulation eines KI-Hosts: Ollama antwortet erst, wenn Docker und
    Container laufen. Die Uhr springt beim Schlafen vor."""

    def __init__(self, docker=True, container=False, ollama_startet=True):
        self.docker, self.container, self.ollama_startet = docker, container, ollama_startet
        self.jetzt = 0.0
        self.aufrufe: list[str] = []

    def modelle_lesen(self):
        if self.docker and self.container and self.ollama_startet:
            return MODELLE
        raise ConnectionError("All connection attempts failed")

    def steuer_status(self):
        return {"docker": self.docker, "containers": [{"name": "ollama", "running": self.container}]}

    def docker_starten(self):
        self.aufrufe.append("docker")
        self.docker = True
        return {"docker": True}

    def container_starten(self, name):
        self.aufrufe.append(f"container:{name}")
        self.container = True
        return {"name": name, "running": True}

    def hilfen(self, **kw):
        return KiStartHilfen(
            modelle_lesen=self.modelle_lesen, steuer_status=self.steuer_status,
            docker_starten=self.docker_starten, container_starten=self.container_starten,
            schlafen=lambda s: setattr(self, "jetzt", self.jetzt + s), uhr=lambda: self.jetzt, **kw,
        )


def test_ollama_laeuft_schon_scannt_nur():
    w = Welt(docker=True, container=True)
    erg = ki_starten(w.hilfen(erwartete_modelle=lambda: ["gemma4", "mistral-small3.2:latest"]))
    assert erg.erfolgreich and erg.modelle == MODELLE
    assert w.aufrufe == []
    # "gemma4" ohne Tag zaehlt als vorhanden (Alias fuer :latest), Mistral fehlt
    assert erg.fehlende_modelle == ["mistral-small3.2:latest"]


def test_container_aus_wird_gestartet():
    w = Welt(docker=True, container=False)
    erg = ki_starten(w.hilfen())
    assert erg.erfolgreich
    assert w.aufrufe == ["container:ollama"]


def test_docker_aus_startet_erst_docker_dann_container():
    w = Welt(docker=False, container=False)
    erg = ki_starten(w.hilfen())
    assert erg.erfolgreich
    assert w.aufrufe == ["docker", "container:ollama"]


def test_container_laeuft_aber_ollama_antwortet_spaeter():
    w = Welt(docker=True, container=True, ollama_startet=False)
    antworten = iter([False, False, True])

    def lesen():
        if next(antworten):
            return MODELLE
        raise ConnectionError("noch nicht")

    h = w.hilfen()
    h.modelle_lesen = lesen
    erg = ki_starten(h)
    assert erg.erfolgreich and w.aufrufe == []  # nichts neu gestartet, nur gewartet


def test_timeout_wenn_ollama_nie_antwortet():
    w = Welt(docker=True, container=True, ollama_startet=False)
    erg = ki_starten(w.hilfen())
    assert not erg.erfolgreich
    assert "antwortet" in erg.fehler
    assert w.jetzt >= ki_start.OLLAMA_WARTEN_SEKUNDEN


def test_ohne_steuerdienst_klare_fehlermeldung():
    def lesen():
        raise ConnectionError("x")

    erg = ki_starten(KiStartHilfen(modelle_lesen=lesen))
    assert not erg.erfolgreich
    assert "Steuer-Dienst" in erg.fehler


def test_docker_start_nicht_moeglich_meldet_fehler():
    w = Welt(docker=False)
    h = w.hilfen()
    h.docker_starten = None
    erg = ki_starten(h)
    assert not erg.erfolgreich and "Docker" in erg.fehler


def test_fehler_beim_containerstart_wird_gemeldet():
    w = Welt(docker=True, container=False)

    def kaputt(name):
        raise RuntimeError("no such container")

    h = w.hilfen()
    h.container_starten = kaputt
    erg = ki_starten(h)
    assert not erg.erfolgreich and "no such container" in erg.fehler


def test_schritte_kommen_live_beim_callback_an():
    w = Welt(docker=False)
    live: list[str] = []
    erg = ki_starten(w.hilfen(), live.append)
    assert live == erg.schritte and len(live) >= 4


# --- API -------------------------------------------------------------------

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
    ssh_targets._ki_start_jobs.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _warte_auf_ende(client, ziel_id, sekunden=5.0):
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        s = client.get(f"/api/ssh-targets/{ziel_id}/ki-starten").json()
        if s["fertig"]:
            return s
        time.sleep(0.05)
    raise AssertionError("Job wurde nicht fertig")


def test_endpunkt_unbekanntes_ziel_404(client):
    assert client.post("/api/ssh-targets/gibt-es-nicht/ki-starten").status_code == 404


def test_endpunkt_status_ohne_job_ist_leer(client):
    s = client.get("/api/ssh-targets/irgendwas/ki-starten").json()
    assert s["laeuft"] is False and s["fertig"] is False


def test_endpunkt_scannt_modelle_und_meldet_fehlende(client, monkeypatch):
    ziel_id = client.post("/api/ssh-targets", json={
        "name": "PC", "host": "http://127.0.0.1:11434", "auth_method": "direct",
    }).json()["id"]
    monkeypatch.setattr(ssh_targets.ollama_client, "tags_sync", lambda url, timeout=10.0: {
        "models": [{"name": "gemma4:latest", "size": 5, "details": {"parameter_size": "7.5B"}}],
    })
    r = client.post(f"/api/ssh-targets/{ziel_id}/ki-starten")
    assert r.status_code == 200
    s = _warte_auf_ende(client, ziel_id)
    assert s["erfolgreich"] is True
    assert [m["name"] for m in s["modelle"]] == ["gemma4:latest"]
    assert "mistral-small3.2:latest" in s["fehlende_modelle"]  # Default-Autor fehlt auf diesem Ziel


def test_endpunkt_meldet_fehler_ohne_steuerdienst(client, monkeypatch):
    ziel_id = client.post("/api/ssh-targets", json={
        "name": "PC", "host": "http://127.0.0.1:11434", "auth_method": "direct",
    }).json()["id"]

    def nicht_erreichbar(url, timeout=10.0):
        raise ConnectionError("All connection attempts failed")

    monkeypatch.setattr(ssh_targets.ollama_client, "tags_sync", nicht_erreichbar)
    client.post(f"/api/ssh-targets/{ziel_id}/ki-starten")
    s = _warte_auf_ende(client, ziel_id)
    assert s["erfolgreich"] is False
    assert "Steuer-Dienst" in s["fehler"]
