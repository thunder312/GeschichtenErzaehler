import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core import projekt_dateien as pd
from app.core.pdf_export import _kapitel_parsen
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
def projekt_mit_kapiteln(client, tmp_path):
    r = client.post("/api/projects", json={"titel": "Der Markt von Rothenfeld", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\n\n## Titel\nDer Markt von Rothenfeld\n",
    })
    projekt_pfad = tmp_path / "projects" / ordner / "projekt"
    # Kapitel 1 real oft FETT (steht hinter der generierten Titelseite),
    # Kapitel 2+ vom Autor-Modell haeufig OHNE Markdown-Fett - beide Formen
    # muss der PDF-Export gleich behandeln (siehe test_kapitel_parsen_*).
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "**Kapitel eins: Der Anfang**\n\nEin Testabsatz.")
    pd.schreib(pd.kapitel_datei(projekt_pfad, 2), "Kapitel zwei: Die Wendung\n\nEin weiterer Absatz.")
    return ordner


def test_export_pdf_liefert_gueltiges_pdf(client, projekt_mit_kapiteln):
    r = client.get(f"/api/projects/{projekt_mit_kapiteln}/export/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_export_pdf_ohne_kapitel_liefert_404(client):
    r = client.post("/api/projects", json={"titel": "Leeres Projekt", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    r2 = client.get(f"/api/projects/{ordner}/export/pdf")
    assert r2.status_code == 404


def test_kapitel_parsen_erkennt_ueberschrift_ohne_markdown_fett():
    # Regression: das Autor-Modell setzt die Kapitelueberschrift nicht
    # zuverlaessig in "**...**" - ohne Fett wurde die Zeile bisher als
    # gewoehnlicher Absatz mitgerendert (falsche Schrift/Ausrichtung,
    # Kapitelname erscheint doppelt neben der roemisch nummerierten
    # Ueberschrift).
    text = "Kapitel zwei: Das Schicksal im Stahl\n\nDer Tag hatte sich in eine Nacht verwandelt."
    untertitel, absaetze = _kapitel_parsen(text)
    assert untertitel == "Das Schicksal im Stahl"
    assert absaetze == ["Der Tag hatte sich in eine Nacht verwandelt."]


def test_kapitel_parsen_erkennt_ueberschrift_mit_markdown_fett():
    text = "**Kapitel eins: Der Ruf des Feuers**\n\nDer Rauch der Schmiedefeuer hing schwer in der Luft."
    untertitel, absaetze = _kapitel_parsen(text)
    assert untertitel == "Der Ruf des Feuers"
    assert absaetze == ["Der Rauch der Schmiedefeuer hing schwer in der Luft."]


def test_kapitel_parsen_ueberspringt_titelseite_vor_ueberschrift():
    text = (
        "# Im Feuer gestählt\n\n"
        "*Eine Geschichte aus dem Mittelalter im Jahre 1125*\n\n"
        "**Kapitel eins: Der Ruf des Feuers**\n\n"
        "Der Rauch der Schmiedefeuer hing schwer in der Luft."
    )
    untertitel, absaetze = _kapitel_parsen(text)
    assert untertitel == "Der Ruf des Feuers"
    assert absaetze == ["Der Rauch der Schmiedefeuer hing schwer in der Luft."]
