import pytest
from fastapi.testclient import TestClient

from app.api import architekt as api_arch
from app.config import Settings, get_settings
from app.core.ollama_client import OllamaFehler
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


GERUEST_ENTWURF = "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\n\n## Titel\nDer Markt von Rothenfeld\n"


def test_architekt_extraktion_liefert_vorlage_aus_handlungstext(client, projekt, monkeypatch):
    aufrufe = []

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        aufrufe.append((rolle, system, user))
        return GERUEST_ENTWURF, {}

    monkeypatch.setattr(api_arch, "sammle_antwort", fake_sammle_antwort)

    r = client.post(
        f"/api/projects/{projekt}/architekt-extraktion",
        json={"handlungstext": "Es war einmal ein Markt in Rothenfeld..."},
    )

    assert r.status_code == 200
    assert r.json() == {"vorlage": GERUEST_ENTWURF}
    assert len(aufrufe) == 1
    rolle, system, user = aufrufe[0]
    assert rolle == "architekt"
    assert "# STORY-GERUEST" in system
    assert user == "Es war einmal ein Markt in Rothenfeld..."


def test_architekt_extraktion_leerer_handlungstext_liefert_422(client, projekt):
    r = client.post(f"/api/projects/{projekt}/architekt-extraktion", json={"handlungstext": ""})
    assert r.status_code == 422


def test_architekt_extraktion_unbekanntes_projekt_liefert_404(client):
    r = client.post("/api/projects/nicht-vorhanden/architekt-extraktion", json={"handlungstext": "Text"})
    assert r.status_code == 404


def test_architekt_extraktion_gibt_ollama_fehler_als_502_weiter(client, projekt, monkeypatch):
    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        raise OllamaFehler("Ollama nicht erreichbar")

    monkeypatch.setattr(api_arch, "sammle_antwort", fake_sammle_antwort)

    r = client.post(f"/api/projects/{projekt}/architekt-extraktion", json={"handlungstext": "Text"})
    assert r.status_code == 502
