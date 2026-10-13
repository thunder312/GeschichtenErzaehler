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
    assert d["abschnitte"] == 2  # zwei Kapitel -> zwei Schritte (nie ueber eine Kapitelgrenze)
    assert d["geschaetzte_minuten"] == 2 * uebs.MINUTEN_JE_ABSCHNITT


def test_uebersetzen_mit_fuelltext_entfernen_und_ergebnis(client, monkeypatch):
    fake, aufrufe = _fake()
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    r = client.post("/api/analysator/uebersetzen",
                    json={"text": TEXT, "dateiname": "Story.md", "fuelltext_entfernen": True})
    assert r.status_code == 202
    assert r.json()["dateiname"] == "Story_de.md"

    status = client.get("/api/analysator/uebersetzen/status").json()
    assert status["abgeschlossen"] is True and status["laeuft"] is False and status["fehler"] is None
    assert status["fuelltext_entfernt"] == 3 and status["gesamt"] == 2

    ergebnis = client.get("/api/analysator/uebersetzen/ergebnis").text
    assert "DE: He walked home." in ergebnis and "DE: Chapter Two" in ergebnis
    assert "Disclaimer" not in ergebnis and "Please review" not in ergebnis
    assert "\n\n" in ergebnis  # Absatzformat bleibt
    assert len(aufrufe) == 2  # ein Schritt je Kapitel


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


# --- Kapitelweise Zwischenstaende und Fortsetzen ----------------------------------

DREI_KAPITEL = (
    "Chapter One\n\nEr ging heim.\n\nSie wartete.\n\n"
    "Chapter Two\n\nEs regnete.\n\nNiemand kam.\n\n"
    "Chapter Three\n\nDas Ende.\n\nUnd Schluss."
)


def test_kapitel_einteilen_und_plan_ueber_kapitelgrenzen():
    einheiten, _ = uebs.einheiten_bilden(DREI_KAPITEL)
    kapitel = uebs.kapitel_einteilen(einheiten)
    assert [(k.titel, k.start, k.ende) for k in kapitel] == [("Chapter One", 0, 3), ("Chapter Two", 3, 6), ("Chapter Three", 6, 9)]
    plan = uebs.plan_bauen(einheiten, kapitel)
    assert [(s.kapitel, len(s.absaetze), s.kapitel_ende) for s in plan] == [(0, 3, True), (1, 3, True), (2, 3, True)]
    # Fortsetzen nach 4 uebersetzten Absaetzen: Kapitel 2 wird ab Absatz 5 neu geplant
    rest = uebs.plan_bauen(einheiten, kapitel, bereits_fertig=4)
    assert [(s.kapitel, len(s.absaetze)) for s in rest] == [(1, 2), (2, 3)]
    assert uebs.fertige_kapitel(kapitel, 4) == (1, 3)
    assert uebs.fertige_kapitel(kapitel, 0) == (0, 0)


def test_ohne_kapitel_entstehen_bloecke_an_szenentrennern():
    absatz = "Wort " * 600
    einheiten = [absatz.strip()] * 4 + ["***"] + [absatz.strip()] * 4
    kapitel = uebs.kapitel_einteilen(einheiten)
    assert len(kapitel) >= 2
    assert kapitel[0].titel == "Teil 1" and kapitel[0].start == 0
    assert kapitel[-1].ende == len(einheiten)
    # lueckenlos und ohne Ueberlappung
    assert all(a.ende == b.start for a, b in zip(kapitel, kapitel[1:]))
    # Szenentrenner ist Blockende, wenn der Block schon gross genug ist
    assert kapitel[0].ende == 5 and len(kapitel) == 2


def _stop_nach_erstem_aufruf(wurzel, aufrufe):
    fake, _ = _fake()

    async def f(base_url, rolle, system, user, **kwargs):
        ergebnis = await fake(base_url, rolle, system, user, **kwargs)
        aufrufe.append(user)
        if len(aufrufe) == 1:
            status = uebs.status_lesen(wurzel)
            status["stop_angefordert"] = True  # wie ein Klick auf "Stoppen" waehrend des ersten Schritts
            uebs.status_schreiben(wurzel, status)
        return ergebnis

    return f


def _wurzel():
    from app.services import projekte_wurzel
    return projekte_wurzel(app.dependency_overrides[get_settings](), "daniel")


def test_zwischenstand_zeigt_nur_fertige_kapitel_und_legt_kapitel_dateien_an(client, monkeypatch):
    wurzel = _wurzel()
    aufrufe: list[str] = []
    monkeypatch.setattr(analysator_api, "sammle_antwort", _stop_nach_erstem_aufruf(wurzel, aufrufe))
    client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "Buch.md"})

    status = client.get("/api/analysator/uebersetzen/status").json()
    assert status["gestoppt"] is True and status["abgeschlossen"] is False
    assert status["kapitel_gesamt"] == 3 and status["kapitel_fertig"] == 1
    assert status["woerter_fertig"] > 0 and status["woerter_gesamt"] > status["woerter_fertig"]

    zwischen = client.get("/api/analysator/uebersetzen/ergebnis?zwischenstand=true").text
    assert "DE: Chapter One" in zwischen and "DE: Er ging heim." in zwischen
    assert "Chapter Two" not in zwischen
    kapitel_datei = uebs.ordner(wurzel) / "Buch_de_Kapitel" / "Kapitel_01.txt"
    assert kapitel_datei.is_file() and "DE: Sie wartete." in kapitel_datei.read_text(encoding="utf-8")

    pdf = client.get("/api/analysator/uebersetzen/pdf?zwischenstand=true")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert 'filename="Buch_de_Zwischenstand.md"' in pdf.headers["content-disposition"] or "Zwischenstand" in pdf.headers["content-disposition"]


def test_zwischenstand_ohne_fertiges_kapitel_ist_404(client):
    assert client.get("/api/analysator/uebersetzen/ergebnis?zwischenstand=true").status_code == 404


def test_fortsetzen_uebersetzt_nur_den_rest(client, monkeypatch):
    wurzel = _wurzel()
    aufrufe: list[str] = []
    monkeypatch.setattr(analysator_api, "sammle_antwort", _stop_nach_erstem_aufruf(wurzel, aufrufe))
    client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "Buch.txt", "fuelltext_entfernen": False})
    assert len(aufrufe) == 1

    fake, aufrufe2 = _fake()
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    r = client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "Buch.txt", "fortsetzen": True})
    assert r.status_code == 202
    status = client.get("/api/analysator/uebersetzen/status").json()
    assert status["abgeschlossen"] is True and status["fortgesetzt"] is True and status["fehler"] is None
    assert len(aufrufe2) == 2  # nur Kapitel 2 und 3, Kapitel 1 wird NICHT noch einmal uebersetzt
    absaetze = client.get("/api/analysator/uebersetzen/ergebnis").text.strip().split("\n\n")
    assert absaetze == ["DE: " + a for a in DREI_KAPITEL.split("\n\n")]  # lueckenlos, richtige Reihenfolge, nichts doppelt
    assert status["kapitel_fertig"] == 3
    assert any("Fortgesetzt ab Absatz 4" in z for z in status["log"])


def test_fortsetzen_mit_geaendertem_text_wird_abgelehnt(client, monkeypatch):
    wurzel = _wurzel()
    monkeypatch.setattr(analysator_api, "sammle_antwort", _stop_nach_erstem_aufruf(wurzel, []))
    client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "Buch.txt"})
    fake, aufrufe = _fake()
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL + "\n\nNeuer Absatz.", "dateiname": "Buch.txt", "fortsetzen": True})
    status = client.get("/api/analysator/uebersetzen/status").json()
    assert "unterscheidet sich" in status["fehler"] and aufrufe == []
    assert status["laeuft"] is False


def test_fortsetzen_nur_bei_unterbrochener_uebersetzung_desselben_dokuments(client, monkeypatch):
    fake, _ = _fake()
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    r = client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "A.txt", "fortsetzen": True})
    assert r.status_code == 409  # nichts zum Fortsetzen
    client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "A.txt"})  # laeuft komplett durch
    r = client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "A.txt", "fortsetzen": True})
    assert r.status_code == 409  # bereits abgeschlossen
    wurzel = _wurzel()
    status = uebs.status_lesen(wurzel)
    status["abgeschlossen"] = False
    uebs.status_schreiben(wurzel, status)
    r = client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "B.txt", "fortsetzen": True})
    assert r.status_code == 409  # anderes Dokument


def test_fortsetzen_eines_laufs_der_alten_version_ohne_neue_statusfelder(client, monkeypatch):
    """Stand wie von der ersten Version geschrieben (kein quell_hash, keine Kapitelfelder):
    die Zahl der schon uebersetzten Absaetze ergibt sich aus der Ergebnisdatei."""
    wurzel = _wurzel()
    alt = {k: v for k, v in uebs.LEERER_STATUS.items() if k in (
        "laeuft", "abgeschlossen", "gestoppt", "stop_angefordert", "aktuell", "gesamt", "log", "fehler",
        "dateiname", "ergebnis_woerter", "fuelltext_entfernt")}
    alt.update(dateiname="Buch_de.txt", gestoppt=True, stop_angefordert=True, aktuell=1, gesamt=3, log=["alt"])
    uebs.status_schreiben(wurzel, alt, behalte_stop=False)
    uebs.ergebnis_pfad(wurzel, "Buch_de.txt").write_text("DE: Chapter One\n\nDE: Er ging heim.\n\nDE: Sie wartete.\n", encoding="utf-8")
    fake, aufrufe = _fake()
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    r = client.post("/api/analysator/uebersetzen", json={"text": DREI_KAPITEL, "dateiname": "Buch.txt", "fortsetzen": True})
    assert r.status_code == 202
    status = client.get("/api/analysator/uebersetzen/status").json()
    assert status["abgeschlossen"] is True and status["fehler"] is None and len(aufrufe) == 2
    assert client.get("/api/analysator/uebersetzen/ergebnis").text.count("DE: Chapter") == 3


def test_zeilenmodus_texte_behalten_ihr_format_beim_fortsetzen_zaehlen(client, monkeypatch):
    """Texte ohne Leerzeilen (ein Absatz pro Zeile): Uebersetzungen enthalten keine Zeilenumbrueche,
    sonst stimmte die Absatzzahl beim Fortsetzen nicht."""
    def antwort(absaetze):
        return "\n\n".join("DE: " + a + "\nzweite Zeile" for a in absaetze)  # Modell liefert Zeilenumbruch im Absatz

    fake, _ = _fake(antwort)
    monkeypatch.setattr(analysator_api, "sammle_antwort", fake)
    client.post("/api/analysator/uebersetzen", json={"text": "Eins.\nZwei.\nDrei.", "dateiname": "z.txt"})
    ergebnis = client.get("/api/analysator/uebersetzen/ergebnis").text.strip().split("\n")
    assert len(ergebnis) == 3 and all(z.startswith("DE: ") for z in ergebnis)
