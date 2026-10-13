"""Projekte in einer Epoche ohne Persona-Dateien werden schon beim Anlegen
abgelehnt (Vorfall 2026-10-13: leere Epoche "Unbekannt" -> erst im
Automatikmodus "Datei fehlt: personas/autor.txt")."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import init_db
from app.main import app


@pytest.fixture
def client_und_settings(tmp_path):
    epochen = tmp_path / "epochen"
    (epochen / "Leer").mkdir(parents=True)
    (epochen / "Leer" / ".name").write_text("Leer", encoding="utf-8")
    (epochen / "Voll").mkdir()
    for datei in ("architekt.txt", "autor.txt", "pruefer_anachronismus.txt"):
        (epochen / "Voll" / datei).write_text("x", encoding="utf-8")
    (epochen / "Halb").mkdir()
    (epochen / "Halb" / "autor.txt").write_text("Autor", encoding="utf-8")
    settings = Settings(
        projects_dir=tmp_path / "projects",
        epochen_dir=epochen,
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c, settings
    app.dependency_overrides.clear()


def test_leere_epoche_wird_beim_anlegen_abgelehnt(client_und_settings):
    client, settings = client_und_settings
    r = client.post("/api/projects", json={"titel": "Test", "epoche": "Leer"})
    assert r.status_code == 422
    assert "unvollständig" in r.json()["detail"]
    assert "architekt.txt" in r.json()["detail"] and "autor.txt" in r.json()["detail"]
    assert not any(settings.projects_dir.rglob("personas"))


def test_halbe_epoche_nennt_nur_die_fehlenden_dateien(client_und_settings):
    client, _ = client_und_settings
    r = client.post("/api/projects", json={"titel": "Test", "epoche": "Halb"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "architekt.txt" in detail and "pruefer_anachronismus.txt" in detail
    assert "es fehlen: architekt.txt, pruefer_anachronismus.txt)" in detail


def test_unvollstaendige_zweite_epoche_wird_abgelehnt(client_und_settings):
    client, _ = client_und_settings
    r = client.post("/api/projects", json={"titel": "Test", "epoche": "Voll", "zweite_epoche": "Leer"})
    assert r.status_code == 422
    assert "Epoche 'Leer' ist unvollständig" in r.json()["detail"]


def test_vollstaendige_epoche_wird_angelegt(client_und_settings):
    client, _ = client_und_settings
    r = client.post("/api/projects", json={"titel": "Test", "epoche": "Voll"})
    assert r.status_code == 201
