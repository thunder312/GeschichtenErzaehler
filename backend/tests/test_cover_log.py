import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api import pipeline as api_pipeline
from app.config import Settings, get_settings
from app.core import cover_log as cl
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
    r = client.post("/api/projects", json={"titel": "Testgeschichte", "epoche": "Regency"})
    return r.json()["ordner"]


@pytest.fixture
def bild_ziel_id(client):
    r = client.post("/api/ssh-targets", json={
        "name": "Direktes Bild-Ziel", "host": "http://127.0.0.1:11434",
        "auth_method": "direct", "bildki_port": 7860,
    })
    assert r.status_code == 201
    return r.json()["id"]


def _jpeg_bytes(farbe=(10, 20, 30)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=farbe).save(puffer, format="JPEG")
    return puffer.getvalue()


def test_upload_legt_log_eintrag_mit_kommentar_an(client, projekt):
    r = client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("mein-bild.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"kommentar": "Über Google AI Studio erzeugt"},
    )
    assert r.status_code == 200

    log = client.get(f"/api/projects/{projekt}/cover/log").json()
    assert len(log["eintraege"]) == 1
    eintrag = log["eintraege"][0]
    assert eintrag["herkunft"] == "hochgeladen"
    assert eintrag["kommentar"] == "Über Google AI Studio erzeugt"
    assert eintrag["zeitpunkt"]
    assert log["aktive_id"] == eintrag["id"]

    bild = client.get(f"/api/projects/{projekt}/cover/log/{eintrag['id']}/bild")
    assert bild.status_code == 200
    assert bild.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_generieren_legt_log_eintrag_mit_beiden_prompts_an(client, projekt, bild_ziel_id, monkeypatch):
    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return "medieval market scene", {}

    async def fake_generiere_cover(base_url, prompt, **kwargs):
        return b"\x89PNG\r\n\x1a\nfake"

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)
    monkeypatch.setattr(api_pipeline.bild_generierung, "generiere_cover", fake_generiere_cover)

    r = client.post(
        f"/api/projects/{projekt}/cover/generieren",
        params={"bild_ziel_id": bild_ziel_id},
        json={"prompt": "mittelalterlicher Marktplatz"},
    )
    assert r.status_code == 200

    log = client.get(f"/api/projects/{projekt}/cover/log").json()
    assert len(log["eintraege"]) == 1
    eintrag = log["eintraege"][0]
    assert eintrag["herkunft"] == "generiert"
    assert "mittelalterlicher Marktplatz" in eintrag["prompt_deutsch"]
    assert eintrag["prompt_englisch"] == "medieval market scene"


def test_mehrere_versuche_reihen_sich_im_log_auf(client, projekt):
    client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("erstes.jpg", _jpeg_bytes((10, 20, 30)), "image/jpeg")},
    )
    client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("zweites.jpg", _jpeg_bytes((200, 100, 0)), "image/jpeg")},
    )
    log = client.get(f"/api/projects/{projekt}/cover/log").json()
    assert len(log["eintraege"]) == 2
    assert log["aktive_id"] == log["eintraege"][1]["id"]


def test_kommentar_kann_nachtraeglich_geaendert_werden(client, projekt):
    client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("bild.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    eintrag_id = client.get(f"/api/projects/{projekt}/cover/log").json()["eintraege"][0]["id"]

    r = client.put(
        f"/api/projects/{projekt}/cover/log/{eintrag_id}/kommentar",
        json={"kommentar": "Nachträglich ergänzt"},
    )
    assert r.status_code == 200

    eintrag = client.get(f"/api/projects/{projekt}/cover/log").json()["eintraege"][0]
    assert eintrag["kommentar"] == "Nachträglich ergänzt"


def test_alten_eintrag_aktivieren_stellt_dessen_bild_wieder_her(client, projekt):
    client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("erstes.jpg", _jpeg_bytes((10, 20, 30)), "image/jpeg")},
    )
    erster_id = client.get(f"/api/projects/{projekt}/cover/log").json()["eintraege"][0]["id"]
    client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("zweites.jpg", _jpeg_bytes((200, 100, 0)), "image/jpeg")},
    )

    r = client.post(f"/api/projects/{projekt}/cover/log/{erster_id}/aktivieren")
    assert r.status_code == 200

    aktuelles_cover = Image.open(io.BytesIO(client.get(f"/api/projects/{projekt}/cover").content))
    assert aktuelles_cover.getpixel((0, 0)) == (10, 20, 30)

    log = client.get(f"/api/projects/{projekt}/cover/log").json()
    assert log["aktive_id"] == erster_id


def test_loeschen_entfernt_eintrag_und_raeumt_aktive_id(client, projekt):
    client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("bild.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    eintrag_id = client.get(f"/api/projects/{projekt}/cover/log").json()["eintraege"][0]["id"]

    r = client.post(f"/api/projects/{projekt}/cover/log/{eintrag_id}/loeschen")
    assert r.status_code == 200
    assert r.json() == {"gelöscht": True}

    log = client.get(f"/api/projects/{projekt}/cover/log").json()
    assert log["eintraege"] == []
    assert log["aktive_id"] is None

    assert client.get(f"/api/projects/{projekt}/cover/log/{eintrag_id}/bild").status_code == 404


def test_unbekannter_eintrag_liefert_404(client, projekt):
    assert client.put(
        f"/api/projects/{projekt}/cover/log/unbekannt/kommentar", json={"kommentar": "x"},
    ).status_code == 404
    assert client.post(f"/api/projects/{projekt}/cover/log/unbekannt/aktivieren").status_code == 404
    assert client.post(f"/api/projects/{projekt}/cover/log/unbekannt/loeschen").status_code == 404


def test_log_parsen_serialisieren_roundtrip():
    eintraege = [
        cl.CoverLogEintrag(id="a1", zeitpunkt="2026-09-04T10:00:00+02:00", herkunft="generiert",
                            prompt_deutsch="Ein Text", prompt_englisch="A text", kommentar=""),
        cl.CoverLogEintrag(id="a2", zeitpunkt="2026-09-04T11:00:00+02:00", herkunft="hochgeladen",
                            kommentar="Google AI Studio"),
    ]
    text = cl.log_serialisieren(eintraege, "a2")
    geparst_eintraege, aktive_id = cl.log_parsen(text)
    assert geparst_eintraege == eintraege
    assert aktive_id == "a2"


def test_log_parsen_ist_defensiv_bei_leerem_oder_kaputtem_text():
    assert cl.log_parsen("") == ([], None)
    assert cl.log_parsen("{kaputt") == ([], None)
