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


def test_befunde_anwenden_ueberspringt_verdaechtig_langen_vorschlag():
    """Regression: ein 'vorschlag', der viel laenger ist als die kurze
    fundstelle, sieht eher nach einem liegen gebliebenen Redaktions-
    kommentar oder dupliziertem Text aus als nach einer echten Korrektur -
    siehe befunde_merge.py:vorschlag_verdaechtig."""
    text = "Ein Satz."
    kommentar = (
        "Dieser Abschnitt sollte gekuerzt oder zusammengefasst werden, um "
        "die Wiederholung zu vermeiden."
    )
    befunde = [_befund("Satz", 4, 8, kommentar)]
    neuer_text, protokoll = automatik.befunde_anwenden(text, befunde)
    assert neuer_text == text
    assert protokoll[0]["grund"] == "verdaechtiger_vorschlag"


def test_befunde_anwenden_wendet_kurze_kasuskorrektur_trotz_geringem_wortueberlapp_an():
    """Gegenprobe zum Test oben: eine normale, kurze Genus-/Kasus-Korrektur
    (hier 'kein' -> 'keine') darf NICHT als verdaechtig blockiert werden,
    nur weil sie wenig woertliche Ueberlappung mit der fundstelle hat."""
    text = "Es gab kein Ressourcenverschwendung."
    start = text.index("kein Ressourcenverschwendung")
    ende = start + len("kein Ressourcenverschwendung")
    befunde = [_befund("kein Ressourcenverschwendung", start, ende, "keine Ressourcenverschwendung")]
    neuer_text, protokoll = automatik.befunde_anwenden(text, befunde)
    assert neuer_text == "Es gab keine Ressourcenverschwendung."
    assert protokoll[0]["art"] == "angewendet"


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


def test_zustand_zusammenfassen_resten_bestaetigt_gilt_als_sauber():
    """Per "Pruefung abschliessen"-Button quittierte Reste sollen die
    Projektliste nicht mehr dauerhaft als "Reste pruefen" anzeigen, obwohl
    das Protokoll des Laufs selbst unveraendert bleibt."""
    status = {
        "gestartet_am": "irgendwann", "laeuft": False, "fehler": None, "abgeschlossen": True,
        "resten_bestaetigt": True,
        "protokoll": [{"art": "uebersprungen", "grund": "konflikt"}],
    }
    assert automatik.zustand_zusammenfassen(status) == "abgeschlossen_sauber"


def test_reste_vorhanden_erkennt_uebersprungene_und_unbekannte_woerter():
    assert automatik.reste_vorhanden({"protokoll": [{"art": "uebersprungen"}]}) is True
    assert automatik.reste_vorhanden({"protokoll": [{"art": "rechtschreibung", "unbekannte_woerter": ["X"]}]}) is True
    assert automatik.reste_vorhanden({"protokoll": [{"art": "angewendet"}]}) is False
    assert automatik.reste_vorhanden({"protokoll": []}) is False


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


def test_verwaiste_laeufe_zuruecksetzen_setzt_laeuft_zurueck(tmp_path):
    """Regression 2026-08-12: Ein Backend-Neustart (Deploy, Absturz) waehrend
    eines laufenden Automatik-Laufs killt den Hintergrund-Task, ohne dass
    dessen eigenes finally: status["laeuft"] = False je ausgefuehrt wird -
    ohne Zuruecksetzen beim naechsten Start bliebe der Lauf fuer immer als
    "laeuft" haengen und fortsetzbar() wuerde "Fortsetzen" nie anbieten."""
    laufendes_projekt = tmp_path / "daniel" / "Regency" / "Haengendes-Projekt"
    status = automatik.status_lesen(laufendes_projekt)
    status["laeuft"] = True
    status["gestartet_am"] = "2026-08-12 16:32"
    status["aktuelles_kapitel"] = 5
    status["aktueller_durchlauf"] = 2
    status["log"] = ["Autor schreibt..."]
    automatik.status_schreiben(laufendes_projekt, status)

    fertiges_projekt = tmp_path / "daniel" / "Mittelalter" / "Fertiges-Projekt"
    fertiger_status = automatik.status_lesen(fertiges_projekt)
    fertiger_status["laeuft"] = False
    fertiger_status["abgeschlossen"] = True
    fertiger_status["log"] = ["Automatikmodus abgeschlossen."]
    automatik.status_schreiben(fertiges_projekt, fertiger_status)

    anzahl = automatik.verwaiste_laeufe_zuruecksetzen(tmp_path)
    assert anzahl == 1

    zurueckgesetzt = automatik.status_lesen(laufendes_projekt)
    assert zurueckgesetzt["laeuft"] is False
    assert zurueckgesetzt["aktueller_durchlauf"] is None
    assert automatik.fortsetzbar(zurueckgesetzt) is True
    assert any("Backend-Neustart" in zeile for zeile in zurueckgesetzt["log"])
    # Der Rest des Logs (u.a. der Hinweis, WO genau unterbrochen wurde) bleibt
    # erhalten, statt ueberschrieben zu werden.
    assert "Autor schreibt..." in zurueckgesetzt["log"]

    unveraendert = automatik.status_lesen(fertiges_projekt)
    assert unveraendert["log"] == ["Automatikmodus abgeschlossen."]


def test_verwaiste_laeufe_zuruecksetzen_schreibt_verlauf_eintrag(tmp_path):
    projekt = tmp_path / "daniel" / "Regency" / "Haengendes-Projekt"
    status = automatik.status_lesen(projekt)
    status["laeuft"] = True
    status["gestartet_am"] = "2026-08-12 16:32"
    automatik.status_schreiben(projekt, status)

    automatik.verwaiste_laeufe_zuruecksetzen(tmp_path)

    eintraege = automatik.verlauf_lesen(projekt)
    assert len(eintraege) == 1
    assert eintraege[0]["status"] == "gestoppt"
    assert eintraege[0]["von"] == "2026-08-12 16:32"
    assert eintraege[0]["fortgesetzt"] is False


def test_verwaiste_laeufe_zuruecksetzen_ohne_laufende_laeufe_bleibt_wirkungslos(tmp_path):
    projekt = tmp_path / "daniel" / "Regency" / "Ruhiges-Projekt"
    status = automatik.status_lesen(projekt)
    status["laeuft"] = False
    automatik.status_schreiben(projekt, status)

    assert automatik.verwaiste_laeufe_zuruecksetzen(tmp_path) == 0
    assert automatik.verlauf_lesen(projekt) == []


def test_verlauf_ohne_datei_ist_leer(tmp_path):
    assert automatik.verlauf_lesen(tmp_path) == []


def test_verlauf_eintrag_anhaengen_und_lesen(tmp_path):
    automatik.verlauf_eintrag_anhaengen(tmp_path, {"status": "abgeschlossen", "dauer_sekunden": 10})
    automatik.verlauf_eintrag_anhaengen(tmp_path, {"status": "fehler", "dauer_sekunden": 5})

    eintraege = automatik.verlauf_lesen(tmp_path)
    assert len(eintraege) == 2
    assert eintraege[0]["status"] == "abgeschlossen"
    assert eintraege[1]["status"] == "fehler"
