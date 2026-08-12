import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings, get_settings
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


def _jpeg_bytes() -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(puffer, format="JPEG")
    return puffer.getvalue()


def test_cover_hochladen_und_lesen_roundtrip(client, projekt):
    """Manuell erzeugtes/heruntergeladenes Titelbild (z.B. kostenlos ueber
    Google AI Studio erstellt) laesst sich ohne konfiguriertes Bild-KI-Ziel
    direkt hochladen und landet als PNG unter demselben /cover-Endpunkt, den
    auch die KI-Generierung befuellt."""
    r = client.get(f"/api/projects/{projekt}/cover")
    assert r.status_code == 404

    r = client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("mein-bild.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert r.status_code == 200
    assert r.json() == {"gespeichert": True}

    r = client.get(f"/api/projects/{projekt}/cover")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_cover_hochladen_lehnt_ungueltige_datei_ab(client, projekt):
    r = client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("nix.txt", b"das hier ist kein Bild", "text/plain")},
    )
    assert r.status_code == 400
    assert client.get(f"/api/projects/{projekt}/cover").status_code == 404


def test_cover_hochladen_ueberschreibt_vorhandenes_cover(client, projekt):
    client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("erstes.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    zweites = io.BytesIO()
    Image.new("RGB", (16, 16), color=(200, 100, 0)).save(zweites, format="PNG")
    r = client.post(
        f"/api/projects/{projekt}/cover/hochladen",
        files={"datei": ("zweites.png", zweites.getvalue(), "image/png")},
    )
    assert r.status_code == 200

    gelesen = client.get(f"/api/projects/{projekt}/cover").content
    neu_dekodiert = Image.open(io.BytesIO(gelesen))
    assert neu_dekodiert.getpixel((0, 0)) == (200, 100, 0)
