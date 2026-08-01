from app.core import automatik


def _befund(fundstelle, start, end, vorschlag, konflikt=False, gefunden=True):
    return {
        "fundstelle": fundstelle, "start": start, "end": end,
        "vorschlag": vorschlag, "konflikt": konflikt, "gefunden": gefunden,
    }


def test_befunde_anwenden_ohne_funde_aendert_nichts():
    text = "Ein Satz. Noch einer."
    neuer_text, protokoll = automatik.befunde_anwenden(text, [])
    assert neuer_text == text
    assert protokoll == []


def test_befunde_anwenden_wendet_einen_fund_an():
    text = "Er ging zu Fuss."
    start = text.index("Fuss")
    befunde = [_befund("Fuss", start, start + len("Fuss"), "Fuß")]
    neuer_text, protokoll = automatik.befunde_anwenden(text, befunde)
    assert neuer_text == "Er ging zu Fuß."
    assert protokoll == [{"art": "angewendet", "grund": None, "fundstelle": "Fuss", "vorschlag": "Fuß"}]


def test_befunde_anwenden_mehrere_nicht_ueberlappende_funde_unabhaengig_von_reihenfolge():
    text = "Der Hund und die Katze rennen."
    befunde_in_reihenfolge = [
        _befund("Hund", 4, 8, "Hunde"),
        _befund("Katze", 17, 22, "Katzen"),
    ]
    befunde_umgekehrt = list(reversed(befunde_in_reihenfolge))

    ergebnis1, _ = automatik.befunde_anwenden(text, befunde_in_reihenfolge)
    ergebnis2, _ = automatik.befunde_anwenden(text, befunde_umgekehrt)

    erwartet = "Der Hunde und die Katzen rennen."
    assert ergebnis1 == erwartet
    assert ergebnis2 == erwartet


def test_befunde_anwenden_ueberspringt_konflikt():
    text = "Ein strittiger Satz."
    befunde = [_befund("strittiger", 4, 14, "unstrittiger", konflikt=True)]
    neuer_text, protokoll = automatik.befunde_anwenden(text, befunde)
    assert neuer_text == text
    assert protokoll == [{"art": "uebersprungen", "grund": "konflikt", "fundstelle": "strittiger", "vorschlag": "unstrittiger"}]


def test_befunde_anwenden_ueberspringt_nicht_gefunden():
    text = "Ein Satz."
    befunde = [_befund("nicht vorhanden", None, None, "Ersatz", gefunden=False)]
    neuer_text, protokoll = automatik.befunde_anwenden(text, befunde)
    assert neuer_text == text
    assert protokoll[0]["grund"] == "nicht_gefunden"


def test_befunde_anwenden_ueberspringt_ohne_vorschlag():
    text = "Ein Satz."
    befunde = [_befund("Ein Satz", 0, 8, None)]
    neuer_text, protokoll = automatik.befunde_anwenden(text, befunde)
    assert neuer_text == text
    assert protokoll[0]["grund"] == "kein_vorschlag"


def test_befunde_anwenden_fund_am_textanfang_und_ende():
    text = "AAA Mitte ZZZ"
    befunde = [
        _befund("AAA", 0, 3, "XXX"),
        _befund("ZZZ", 10, 13, "YYY"),
    ]
    neuer_text, _ = automatik.befunde_anwenden(text, befunde)
    assert neuer_text == "XXX Mitte YYY"


def test_status_lesen_ohne_datei_liefert_leerzustand(tmp_path):
    status = automatik.status_lesen(tmp_path)
    assert status["laeuft"] is False
    assert status["log"] == []
    assert status["abgeschlossen"] is False


def test_zustand_zusammenfassen_nie_gestartet(tmp_path):
    status = automatik.status_lesen(tmp_path)
    assert automatik.zustand_zusammenfassen(status) is None


def test_zustand_zusammenfassen_laeuft():
    status = {"gestartet_am": "irgendwann", "laeuft": True, "fehler": None, "protokoll": []}
    assert automatik.zustand_zusammenfassen(status) == "laeuft"


def test_zustand_zusammenfassen_fehler():
    status = {"gestartet_am": "irgendwann", "laeuft": False, "fehler": "Ollama nicht erreichbar", "protokoll": []}
    assert automatik.zustand_zusammenfassen(status) == "fehler"


def test_zustand_zusammenfassen_sauber_abgeschlossen():
    status = {
        "gestartet_am": "irgendwann", "laeuft": False, "fehler": None, "abgeschlossen": True,
        "protokoll": [{"art": "angewendet"}, {"art": "rechtschreibung", "unbekannte_woerter": []}],
    }
    assert automatik.zustand_zusammenfassen(status) == "abgeschlossen_sauber"


def test_zustand_zusammenfassen_mit_uebersprungenen_resten():
    status = {
        "gestartet_am": "irgendwann", "laeuft": False, "fehler": None, "abgeschlossen": True,
        "protokoll": [{"art": "angewendet"}, {"art": "uebersprungen", "grund": "konflikt"}],
    }
    assert automatik.zustand_zusammenfassen(status) == "abgeschlossen_mit_resten"


def test_zustand_zusammenfassen_mit_unbekannten_woertern():
    status = {
        "gestartet_am": "irgendwann", "laeuft": False, "fehler": None, "abgeschlossen": True,
        "protokoll": [{"art": "rechtschreibung", "unbekannte_woerter": ["Foobar"]}],
    }
    assert automatik.zustand_zusammenfassen(status) == "abgeschlossen_mit_resten"


def test_zustand_zusammenfassen_gestoppt_vor_abschluss():
    """Ein per Stop-Klick (oder Absturz) unterbrochener, noch nicht
    abgeschlossener Lauf soll NICHT als "abgeschlossen_*" in der
    Projektliste auftauchen, auch wenn das Protokoll schon Eintraege
    enthaelt - sonst wuerde ein ueber "Fortsetzen" noch weiterzufuehrender
    Lauf faelschlich als fertig wirken."""
    status = {
        "gestartet_am": "irgendwann", "laeuft": False, "fehler": None, "abgeschlossen": False,
        "protokoll": [{"art": "angewendet"}],
    }
    assert automatik.zustand_zusammenfassen(status) == "gestoppt"


def test_status_schreiben_und_lesen_roundtrip(tmp_path):
    status = automatik.status_lesen(tmp_path)
    status["laeuft"] = True
    status["aktuelles_kapitel"] = 3
    status["log"].append("Kapitel 3 wird geschrieben...")

    automatik.status_schreiben(tmp_path, status)
    gelesen = automatik.status_lesen(tmp_path)

    assert gelesen["laeuft"] is True
    assert gelesen["aktuelles_kapitel"] == 3
    assert gelesen["log"] == ["Kapitel 3 wird geschrieben..."]


def test_status_lesen_ergaenzt_aktueller_durchlauf_bei_alten_dateien(tmp_path):
    """Status-Dateien aus der Zeit vor diesem Feld duerfen nicht mit einem
    KeyError/ValidationError abgewiesen werden."""
    import json
    pfad = tmp_path / "projekt" / automatik.AUTOMATIK_STATUS_DATEINAME
    pfad.parent.mkdir(parents=True)
    alt = automatik.status_lesen(tmp_path)
    del alt["aktueller_durchlauf"]
    pfad.write_text(json.dumps(alt), encoding="utf-8")

    gelesen = automatik.status_lesen(tmp_path)
    assert gelesen["aktueller_durchlauf"] is None


def test_fortsetzbar_nie_gestartet():
    status = {"gestartet_am": None, "laeuft": False, "abgeschlossen": False}
    assert automatik.fortsetzbar(status) is False


def test_fortsetzbar_waehrend_lauf():
    status = {"gestartet_am": "irgendwann", "laeuft": True, "abgeschlossen": False}
    assert automatik.fortsetzbar(status) is False


def test_fortsetzbar_nach_sauberem_abschluss():
    status = {"gestartet_am": "irgendwann", "laeuft": False, "abgeschlossen": True}
    assert automatik.fortsetzbar(status) is False


def test_fortsetzbar_nach_fehler_oder_stop():
    status = {"gestartet_am": "irgendwann", "laeuft": False, "abgeschlossen": False}
    assert automatik.fortsetzbar(status) is True


def test_verlauf_ohne_datei_ist_leer(tmp_path):
    assert automatik.verlauf_lesen(tmp_path) == []


def test_verlauf_eintrag_anhaengen_und_lesen(tmp_path):
    automatik.verlauf_eintrag_anhaengen(tmp_path, {"status": "abgeschlossen", "dauer_sekunden": 10})
    automatik.verlauf_eintrag_anhaengen(tmp_path, {"status": "fehler", "dauer_sekunden": 5})

    eintraege = automatik.verlauf_lesen(tmp_path)
    assert len(eintraege) == 2
    assert eintraege[0]["status"] == "abgeschlossen"
    assert eintraege[1]["status"] == "fehler"
