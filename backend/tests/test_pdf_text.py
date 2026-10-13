"""Tests fuer app/core/pdf_text.py und POST /api/analysator/pdf-text -
PDFs werden mit reportlab erzeugt (kein Fixture-File noetig)."""
import io

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen import canvas

from app.config import Settings, get_settings
from app.core import analysator as an
from app.core import pdf_text
from app.db import init_db
from app.main import app


def _pdf(seiten: list[list[str]], kopfzeile: str | None = None) -> bytes:
    """Jede Seite = Liste von Zeilen (so wie im PDF umbrochen)."""
    puffer = io.BytesIO()
    c = canvas.Canvas(puffer, pagesize=A5)
    for nr, zeilen in enumerate(seiten, start=1):
        y = 540
        if kopfzeile:
            c.drawString(40, 570, f"{kopfzeile} {nr}")
        for z in zeilen:
            c.drawString(40, y, z)
            y -= 14
        c.drawString(190, 20, str(nr))
        c.showPage()
    c.save()
    return puffer.getvalue()


# Eine Zeile "voller Breite" (lang), Absatzende = kurze Zeile. Jede Wiederholung
# (k) hat eigene Woerter, damit die Kopf-/Fusszeilen-Erkennung nichts entfernt.
WOERTER = ["langen", "engen", "kalten"]


def lang(k: int = 0) -> str:
    return f"Er ging durch den {WOERTER[k]} dunklen Gang des alten Hauses und hoerte nur seine Schritte"


def seiten(wiederholungen: int = 3) -> list[list[str]]:
    ergebnis: list[list[str]] = []
    for k in range(wiederholungen):
        ergebnis += [
            ["Chapter One",
             lang(k), "auf dem Steinboden hallen.",
             lang(k), "und dann ein leises Geraeusch.",
             "A/N: Danke fuer das Lesen!"],
            [lang(k), "wurde ihm klar, dass jemand da war.",
             "Chapter Two",
             lang(k), "ein Licht unter der Tuer."] + ["Noch ein Satz zum Auffuellen der Wortzahl hier."] * 3,
        ]
    return ergebnis


def test_absaetze_werden_rekonstruiert_und_ueberschriften_isoliert():
    ergebnis = pdf_text.pdf_text_extrahieren(_pdf(seiten()), an.KAPITEL_STICHWORT_MUSTER)
    assert ergebnis.seiten == 6
    absaetze = ergebnis.text.split("\n\n")
    assert absaetze[0] == "Chapter One"
    # Umbrochene Zeilen sind wieder EIN Absatz
    assert absaetze[1] == lang(0) + " auf dem Steinboden hallen."
    assert "A/N: Danke fuer das Lesen!" in absaetze
    # Seitenzahlen (reine Ziffernzeile) sind entfernt
    assert "1" not in absaetze and "2" not in absaetze


def test_laufende_kopfzeile_wird_entfernt():
    ergebnis = pdf_text.pdf_text_extrahieren(_pdf(seiten(), kopfzeile="Mein Roman - Seite"))
    assert "Mein Roman" not in ergebnis.text


def test_pdf_ergebnis_geht_durch_vorbereiten(tmp_path):
    v = an.vorbereiten(pdf_text.pdf_text_extrahieren(_pdf(seiten()), an.KAPITEL_STICHWORT_MUSTER).text)
    assert v.kapitel_quelle == "stichwort"
    assert len(v.abschnitte) == 6
    assert len(v.entfernt) == 3  # drei A/N-Zeilen


def test_pdf_ohne_text_wird_abgelehnt():
    leer = _pdf([[]])
    with pytest.raises(pdf_text.PdfFehler, match="kein Text"):
        pdf_text.pdf_text_extrahieren(leer)


def test_kein_pdf_wird_abgelehnt():
    with pytest.raises(pdf_text.PdfFehler):
        pdf_text.pdf_text_extrahieren(b"das ist kein pdf")


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
        epochen_dir=tmp_path / "epochen",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_endpunkt_liefert_text_seiten_und_woerter(client):
    r = client.post("/api/analysator/pdf-text", files={"datei": ("x.pdf", _pdf(seiten()), "application/pdf")})
    assert r.status_code == 200
    daten = r.json()
    assert daten["seiten"] == 6
    assert daten["woerter"] > 30
    assert daten["text"].startswith("Chapter One")


def test_endpunkt_meldet_fehler_als_422(client):
    r = client.post("/api/analysator/pdf-text", files={"datei": ("x.pdf", b"kein pdf", "application/pdf")})
    assert r.status_code == 422
    assert "PDF" in r.json()["detail"]
