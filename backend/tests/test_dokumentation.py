import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import init_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    (tmp_path / "Anleitung.md").write_text("# Testanleitung\n\nEin Absatz mit Umlauten: äöüß.", encoding="utf-8")
    (tmp_path / "Hilfe.md").write_text("# Testhilfe\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")

    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        anleitung_md=tmp_path / "Anleitung.md",
        hilfe_md=tmp_path / "Hilfe.md",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_anleitung_liefert_gerendertes_html(client):
    r = client.get("/api/docs/anleitung")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<h1>Testanleitung</h1>" in r.text
    assert "äöüß" in r.text


def test_hilfe_liefert_gerendertes_html_mit_tabelle(client):
    r = client.get("/api/docs/hilfe")
    assert r.status_code == 200
    assert "<h1>Testhilfe</h1>" in r.text
    assert "<table>" in r.text


def test_anleitung_fehlende_datei_liefert_404(client, tmp_path):
    (tmp_path / "Anleitung.md").unlink()
    r = client.get("/api/docs/anleitung")
    assert r.status_code == 404
