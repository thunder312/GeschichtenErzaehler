import io

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
    projekt_pfad = tmp_path / "projects" / "daniel" / ordner / "projekt"
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


def test_export_pdf_mit_cover_fuegt_bildseite_ein(client, projekt_mit_kapiteln, tmp_path):
    import io

    from PIL import Image as PILImage

    projekt_pfad = tmp_path / "projects" / "daniel" / projekt_mit_kapiteln / "projekt"
    puffer = io.BytesIO()
    PILImage.new("RGB", (256, 256), color="blue").save(puffer, format="PNG")
    pd.cover_datei(projekt_pfad).write_bytes(puffer.getvalue())

    mit_cover = client.get(f"/api/projects/{projekt_mit_kapiteln}/export/pdf")
    assert mit_cover.status_code == 200
    assert mit_cover.content.startswith(b"%PDF")

    # Grobe Regression-Absicherung, dass das Cover tatsaechlich eine
    # zusaetzliche Seite einfuegt, ohne den PDF-Inhalt komplett zu parsen.
    pd.cover_datei(projekt_pfad).unlink()
    ohne_cover = client.get(f"/api/projects/{projekt_mit_kapiteln}/export/pdf")
    assert len(mit_cover.content) != len(ohne_cover.content)


def test_export_pdf_mit_hochformat_cover_ueberlaeuft_nicht(client, projekt_mit_kapiteln, tmp_path):
    # Regression: ein Cover, dessen Seitenverhaeltnis die Skalierung an der
    # Rahmenhoehe (statt -breite) ausrichtet, ragte um genau das reportlab-
    # Standard-Frame-Padding (6pt je Seite) ueber den Inhaltsbereich hinaus
    # und liess buch_pdf_erzeugen() mit einem LayoutError abstuerzen (Live-
    # Vorfall "Asche-und-Kimono...", Seitenverhaeltnis ca. 512x917).
    import io

    from PIL import Image as PILImage

    projekt_pfad = tmp_path / "projects" / "daniel" / projekt_mit_kapiteln / "projekt"
    puffer = io.BytesIO()
    PILImage.new("RGB", (512, 917), color="blue").save(puffer, format="PNG")
    pd.cover_datei(projekt_pfad).write_bytes(puffer.getvalue())

    r = client.get(f"/api/projects/{projekt_mit_kapiteln}/export/pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")


def test_export_pdf_ohne_cover_bleibt_unveraendert(client, projekt_mit_kapiteln):
    r = client.get(f"/api/projects/{projekt_mit_kapiteln}/export/pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")


def test_export_pdf_stellt_sonderzeichen_korrekt_dar(client, projekt_mit_kapiteln, tmp_path):
    # Regression: die eingebauten reportlab-Kernschriften (Times-Roman etc.)
    # sind an WinAnsiEncoding gebunden und koennen Zeichen ausserhalb von
    # Latin-1 nicht darstellen - reportlab ersetzt sie dabei nicht durch "?",
    # sondern still durch ein voellig unpassendes Symbol aus der internen
    # ZapfDingbats-Fallback-Schrift (z.B. bei "ō" im Figurennamen "Genzō").
    from pypdf import PdfReader

    projekt_pfad = tmp_path / "projects" / "daniel" / projekt_mit_kapiteln / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "**Kapitel eins: Genzō und der Verrat**\n\nGenzō war ein Spion.")

    r = client.get(f"/api/projects/{projekt_mit_kapiteln}/export/pdf")
    assert r.status_code == 200

    text = "".join(seite.extract_text() for seite in PdfReader(io.BytesIO(r.content)).pages)
    assert "Genzō" in text
    assert b"ZapfDingbats" not in r.content


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
