"""Tests fuer app/core/uebersetzer.py und die Uebersetzen-Endpunkte im Analysator
(Ollama gemockt)."""
import pytest
from fastapi.testclient import TestClient

import app.api.analysator as analysator_api
from app.config import Settings, get_settings
from app.core import uebersetzer as uebs
from app.db import init_db
from app.main import app


def test_dateiname_de():
    assert uebs.dateiname_de("Geschichte.pdf") == "Geschichte_de.pdf"
    assert uebs.dateiname_de("The Story.md") == "The Story_de.md"
    assert uebs.dateiname_de("notiz") == "notiz_de.txt"
    assert uebs.dateiname_de("Text_de.txt") == "Text_de.txt"  # kein _de_de
    assert uebs.dateiname_de("a/b:c.txt") == "b-c_de.txt" or uebs.dateiname_de("a/b:c.txt").endswith("_de.txt")
    assert uebs.dateiname_de("Roman.docx") == "Roman_de.txt"  # unbekannte Endung -> txt


def test_abschnitte_bilden_teilt_nur_an_absaetzen():
    absatz = "Wort " * 400
    abschnitte = uebs.abschnitte_bilden("\n\n".join([absatz] * 5), max_woerter=900)
    assert [len(a) for a in abschnitte] == [2, 2, 1]
    assert sum(len(a) for a in abschnitte) == 5
    # Zeilenweise Texte (kein Leerzeilen-Trenner)
    assert uebs.abschnitte_bilden("eins\nzwei\ndrei") == [["eins", "zwei", "drei"]]
    assert uebs.trenner_fuer("a\n\nb") == "\n\n" and uebs.trenner_fuer("a\nb") == "\n"
    assert uebs.abschnitte_bilden("  \n ") == []


def test_antwort_bereinigen():
    assert uebs.antwort_bereinigen("```\nHallo Welt\n```") == "Hallo Welt"
    assert uebs.antwort_bereinigen("Hier ist die Übersetzung:\n\nHallo") == "Hallo"
    assert uebs.antwort_bereinigen("Normaler Text") == "Normaler Text"


def test_text_pdf_erzeugen_liefert_pdf():
    pdf = uebs.text_pdf_erzeugen("Test", "Kapitel eins: Der Sturm\n\nEr ging **schnell** davon, äöüß.\n\nZweiter Absatz.")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


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


def _fake(antworten=None):
    """Fake fuer sammle_antwort: 'übersetzt' jeden Absatz mit Praefix 'DE: '."""
    aufrufe = []

    async def fake(base_url, rolle, system, user, **kwargs):
        aufrufe.append(user)
        absaetze = [a for a in user.split("\n\n")[1:] if a.strip()]
        if antworten is not None:
            return antworten(absaetze), {}
        return "\n\n".join("DE: " + a for a in absaetze), {}

    return fake, aufrufe


TEXT = (
    "Title: Test\n\nDisclaimer: Nicht meins.\n\nChapter One\n\nHe walked home.\n\nShe waited.\n\n"
    "A/N: Please review!\n\nChapter Two\n\nIt rained."
)


def test_fuelltext_vorschau(client):
    r = client.post("/api/analysator/fuelltext-vorschau", json={"text": TEXT})
    assert r.status_code == 200
    d = r.json()
    assert d["fuelltext_absaetze"] == 3  # Title, Disclaimer, A/N
    assert any(b.startswith("Disclaimer") for b in d["beispiele"])
    assert d["abschnitte"] == 1
    assert d["geschaetzte_minuten"] == uebs.MINUTEN_JE_ABSCHNITT


def test_uebersetzen_mit_fuelltext_entfernen_und_ergebnis(client, monkeypatch):
    fake, aufrufe = _fake()
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    r = client.post("/api/analysator/uebersetzen",
                    json={"text": TEXT, "dateiname": "Story.md", "fuelltext_entfernen": True})
    assert r.status_code == 202
    assert r.json()["dateiname"] == "Story_de.md"

    status = client.get("/api/analysator/uebersetzen/status").json()
    assert status["abgeschlossen"] is True and status["laeuft"] is False and status["fehler"] is None
    assert status["fuelltext_entfernt"] == 3 and status["gesamt"] == 1

    ergebnis = client.get("/api/analysator/uebersetzen/ergebnis").text
    assert "DE: He walked home." in ergebnis and "DE: Chapter Two" in ergebnis
    assert "Disclaimer" not in ergebnis and "Please review" not in ergebnis
    assert "\n\n" in ergebnis  # Absatzformat bleibt
    assert len(aufrufe) == 1


def test_uebersetzen_ohne_fuelltext_entfernen_behaelt_alles(client, monkeypatch):
    fake, _ = _fake()
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    client.post("/api/analysator/uebersetzen", json={"text": TEXT, "dateiname": "Story.txt"})
    ergebnis = client.get("/api/analysator/uebersetzen/ergebnis").text
    assert "DE: Disclaimer: Nicht meins." in ergebnis and "DE: A/N: Please review!" in ergebnis


def test_falsche_absatzzahl_loest_absatzweise_wiederholung_aus(client, monkeypatch):
    """Das Modell fasst alle Absaetze eines Abschnitts zusammen -> Abschnitt wird
    Absatz fuer Absatz neu uebersetzt, nichts geht verloren."""
    aufrufe_je_groesse = []

    def antwort(absaetze):
        aufrufe_je_groesse.append(len(absaetze))
        if len(absaetze) > 1:
            return " ".join("DE: " + a for a in absaetze)  # ein einziger Absatz
        return "DE: " + absaetze[0]

    fake, _ = _fake(antwort)
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    client.post("/api/analysator/uebersetzen", json={"text": "Eins.\n\nZwei.\n\nDrei.", "dateiname": "x.txt"})
    ergebnis = client.get("/api/analysator/uebersetzen/ergebnis").text
    assert ergebnis.strip().split("\n\n") == ["DE: Eins.", "DE: Zwei.", "DE: Drei."]
    assert aufrufe_je_groesse == [3, 1, 1, 1]


def test_pdf_ergebnis_fuer_pdf_dokumente(client, monkeypatch):
    fake, _ = _fake()
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    r = client.post("/api/analysator/uebersetzen", json={"text": "He ran.\n\nShe slept.", "dateiname": "Buch.pdf"})
    assert r.json()["dateiname"] == "Buch_de.pdf"
    pdf = client.get("/api/analysator/uebersetzen/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert 'filename="Buch_de.pdf"' in pdf.headers["content-disposition"]
    assert client.get("/api/analysator/uebersetzen/ergebnis").text.startswith("DE: He ran.")


def test_ollama_fehler_wird_im_status_gemeldet(client, monkeypatch):
    from app.core.ollama_client import OllamaFehler

    async def kaputt(*args, **kwargs):
        raise OllamaFehler("Ollama nicht erreichbar")

    async def kein_warten(sekunden):
        return None

    monkeypatch.setattr(analysator_api, "sammle_antwort", kaputt)
    monkeypatch.setattr(analysator_api.asyncio, "sleep", kein_warten)
    client.post("/api/analysator/uebersetzen", json={"text": "Hello.", "dateiname": "x.txt"})
    status = client.get("/api/analysator/uebersetzen/status").json()
    assert status["laeuft"] is False and status["abgeschlossen"] is False
    assert "nicht erreichbar" in status["fehler"]


def test_zweiter_start_waehrend_laufender_uebersetzung_wird_abgewiesen(client, tmp_path):
    settings = app.dependency_overrides[get_settings]()
    from app.services import projekte_wurzel
    wurzel = projekte_wurzel(settings, "daniel")
    uebs.status_schreiben(wurzel, {**uebs.LEERER_STATUS, "log": [], "laeuft": True}, behalte_stop=False)
    r = client.post("/api/analysator/uebersetzen", json={"text": "Hello.", "dateiname": "x.txt"})
    assert r.status_code == 409


def test_stop_haelt_nach_dem_aktuellen_abschnitt_an_und_behaelt_ergebnis(client, monkeypatch):
    absatz = "Wort " * 500
    text = "\n\n".join([absatz.strip() + f" {i}." for i in range(4)])  # 4 Abschnitte (je ~500 Woerter -> 2 je Abschnitt)
    settings = app.dependency_overrides[get_settings]()
    from app.services import projekte_wurzel
    wurzel = projekte_wurzel(settings, "daniel")
    fake, aufrufe = _fake()

    async def stoppender_fake(base_url, rolle, system, user, **kwargs):
        ergebnis = await fake(base_url, rolle, system, user, **kwargs)
        status = uebs.status_lesen(wurzel)
        status["stop_angefordert"] = True  # wie ein Klick auf "Stoppen" waehrend des ersten Abschnitts
        uebs.status_schreiben(wurzel, status)
        return ergebnis

    monkeypatch.setattr(analysator_api, "sammle_antwort", stoppender_fake)
    client.post("/api/analysator/uebersetzen", json={"text": text, "dateiname": "x.txt"})
    status = client.get("/api/analysator/uebersetzen/status").json()
    assert status["gestoppt"] is True and status["abgeschlossen"] is False
    assert status["gesamt"] >= 2 and len(aufrufe) == 1
    assert client.get("/api/analysator/uebersetzen/ergebnis").text.startswith("DE: ")


def test_ergebnis_ohne_uebersetzung_ist_404(client):
    assert client.get("/api/analysator/uebersetzen/ergebnis").status_code == 404
    assert client.get("/api/analysator/uebersetzen/pdf").status_code == 404
