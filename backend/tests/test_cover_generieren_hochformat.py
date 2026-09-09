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


# --- Feature "KI- und Speicherkontrolle": Bild trotz Schreibens -----------

def _speicherkontrolle_an(client):
    client.put("/api/einstellungen", json={
        "speicherkontrolle_aktiv": True,
        "speicherkontrolle_container": ["sd-server", "sd-server-pony"],
    })


def _cover_mocks(monkeypatch, container_laeuft: bool, automatik_laeuft: bool):
    async def fake_sammle_antwort(*a, **k):
        return "english prompt", {}

    async def fake_generiere_cover(base_url, prompt, **kwargs):
        return b"\x89PNG\r\n\x1a\nDATA"

    async def fake_warte(base_url, **k):
        return None

    starts = []
    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)
    monkeypatch.setattr(api_pipeline.bild_generierung, "generiere_cover", fake_generiere_cover)
    monkeypatch.setattr(api_pipeline.bild_generierung, "warte_bis_bereit", fake_warte)
    monkeypatch.setattr(api_pipeline, "athene_steuerung_verfuegbar", lambda *a, **k: True)
    monkeypatch.setattr(api_pipeline, "athene_status", lambda *a, **k: {
        "verfuegbar": True, "ram": {}, "swap": {},
        "containers": [{"name": "sd-server", "running": container_laeuft},
                       {"name": "sd-server-pony", "running": True}],
        "ollama": [],
    })
    monkeypatch.setattr(api_pipeline, "athene_container_setzen",
                        lambda s, z, name, aktion: starts.append((name, aktion)) or {"name": name, "aktion": aktion, "running": True})
    monkeypatch.setattr(api_pipeline.automatik, "status_lesen", lambda pr: {"laeuft": automatik_laeuft})
    return starts


def test_cover_generieren_warnt_wenn_bildki_aus_und_automatik_laeuft(client, projekt, bild_ziel_id, monkeypatch):
    _speicherkontrolle_an(client)
    _cover_mocks(monkeypatch, container_laeuft=False, automatik_laeuft=True)
    r = client.post(
        f"/api/projects/{projekt}/cover/generieren?bild_ziel_id={bild_ziel_id}",
        json={"prompt": "ein Schloss", "bild_modell": "flux"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "bildki_aus_waehrend_schreiben"
    assert r.json()["detail"]["container"] == "sd-server"


def test_cover_generieren_faehrt_bildki_hoch_bei_bestaetigung(client, projekt, bild_ziel_id, monkeypatch):
    _speicherkontrolle_an(client)
    starts = _cover_mocks(monkeypatch, container_laeuft=False, automatik_laeuft=True)
    r = client.post(
        f"/api/projects/{projekt}/cover/generieren?bild_ziel_id={bild_ziel_id}&trotz_schreibens=true",
        json={"prompt": "ein Schloss", "bild_modell": "flux"},
    )
    assert r.status_code == 200
    assert ("sd-server", "start") in starts


def test_cover_generieren_faehrt_bildki_still_hoch_wenn_kein_lauf_aktiv(client, projekt, bild_ziel_id, monkeypatch):
    _speicherkontrolle_an(client)
    starts = _cover_mocks(monkeypatch, container_laeuft=False, automatik_laeuft=False)
    r = client.post(
        f"/api/projects/{projekt}/cover/generieren?bild_ziel_id={bild_ziel_id}",
        json={"prompt": "ein Schloss", "bild_modell": "flux"},
    )
    assert r.status_code == 200
    assert ("sd-server", "start") in starts
