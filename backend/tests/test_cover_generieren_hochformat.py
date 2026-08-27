import pytest
from fastapi.testclient import TestClient

from app.api import pipeline as api_pipeline
from app.config import Settings, get_settings
from app.core import geruest as g
from app.core import projekt_dateien as pd
from app.db import init_db
from app.main import app
from app.services import projekt_pfad


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
    return r.json()["ordner"]


@pytest.fixture
def bild_ziel_id(client):
    r = client.post("/api/ssh-targets", json={
        "name": "Direktes Bild-Ziel", "host": "http://127.0.0.1:11434",
        "auth_method": "direct", "bildki_port": 7860,
    })
    assert r.status_code == 201
    return r.json()["id"]


def test_cover_generieren_stellt_hochformat_praefix_voran(client, projekt, bild_ziel_id, monkeypatch):
    """Ein Buchcover soll wie ein echtes Buchcover im Hochformat wirken statt
    quadratisch wie das sd-server-Standardbild - siehe
    g.COVER_PROMPT_HOCHFORMAT_PRAEFIX."""
    uebersetzung_eingaben = []
    generierung_prompts = []

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        uebersetzung_eingaben.append(user)
        return "portrait orientation, medieval market scene", {}

    async def fake_generiere_cover(base_url, prompt, **kwargs):
        generierung_prompts.append(prompt)
        return b"\x89PNG\r\n\x1a\nfake"

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)
    monkeypatch.setattr(api_pipeline.bild_generierung, "generiere_cover", fake_generiere_cover)

    r = client.post(
        f"/api/projects/{projekt}/cover/generieren",
        params={"bild_ziel_id": bild_ziel_id},
        json={"prompt": "mittelalterlicher Marktplatz, Abendlicht"},
    )
    assert r.status_code == 200
    assert r.json() == {"gespeichert": True}

    assert len(uebersetzung_eingaben) == 1
    assert uebersetzung_eingaben[0] == g.COVER_PROMPT_HOCHFORMAT_PRAEFIX + "mittelalterlicher Marktplatz, Abendlicht"
    assert generierung_prompts == ["portrait orientation, medieval market scene"]


def test_cover_generieren_verdoppelt_praefix_nicht_wenn_bereits_vorhanden(client, projekt, bild_ziel_id, monkeypatch):
    """Kommt der Prompt (z.B. aus dem sichtbaren Vorschlag von
    cover_prompt_vorschlagen()) bereits mit dem Hochformat-Praefix an, darf
    cover_generieren() ihn nicht ein zweites Mal voranstellen - siehe
    g.cover_prompt_hochformat_sicherstellen()."""
    uebersetzung_eingaben = []

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        uebersetzung_eingaben.append(user)
        return "vertical format, medieval market scene", {}

    async def fake_generiere_cover(base_url, prompt, **kwargs):
        return b"\x89PNG\r\n\x1a\nfake"

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)
    monkeypatch.setattr(api_pipeline.bild_generierung, "generiere_cover", fake_generiere_cover)

    r = client.post(
        f"/api/projects/{projekt}/cover/generieren",
        params={"bild_ziel_id": bild_ziel_id},
        json={"prompt": g.COVER_PROMPT_HOCHFORMAT_PRAEFIX + "mittelalterlicher Marktplatz, Abendlicht"},
    )
    assert r.status_code == 200
    assert uebersetzung_eingaben == [g.COVER_PROMPT_HOCHFORMAT_PRAEFIX + "mittelalterlicher Marktplatz, Abendlicht"]


def test_cover_prompt_vorschlagen_zeigt_hochformat_praefix_sichtbar(client, projekt, monkeypatch):
    """Der Praefix soll nicht mehr nur unsichtbar bei der Generierung
    ergaenzt werden, sondern bereits im vorgeschlagenen, editierbaren Prompt
    auftauchen (siehe geruest.py:cover_prompt_hochformat_sicherstellen)."""
    settings = app.dependency_overrides[get_settings]()
    projekt_root = projekt_pfad(settings, settings.default_username, projekt)
    pd.schreib(pd.geruest_datei(projekt_root / "projekt"), "# STORY-GERUEST\n\n## Titel\nTestgeschichte\n")

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return "mittelalterlicher Marktplatz, Abendlicht", {}

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)

    r = client.post(f"/api/projects/{projekt}/cover/prompt-vorschlagen")
    assert r.status_code == 200
    assert r.json()["prompt"] == g.COVER_PROMPT_HOCHFORMAT_PRAEFIX + "mittelalterlicher Marktplatz, Abendlicht"
