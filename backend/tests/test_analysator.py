from app.core import analysator as an


def test_zahlwort_bekannte_zahl():
    assert an.zahlwort(1) == "eins"
    assert an.zahlwort(7) == "sieben"


def test_zahlwort_faellt_bei_unbekannter_zahl_auf_ziffer_zurueck():
    assert an.zahlwort(0) == "0"
    assert an.zahlwort(999) == "999"


def test_text_in_kapitel_teilen_erkennt_ueberschriften():
    text = (
        "Kapitel 1: Der Anfang\n\nEs war einmal ein Held, der auszog. " + "Wort " * 300 + "\n\n"
        "Kapitel 2: Die Wendung\n\nDann geschah etwas Unerwartetes. " + "Wort " * 300
    )
    abschnitte = an.text_in_kapitel_teilen(text)
    assert len(abschnitte) == 2
    assert "Held, der auszog" in abschnitte[0]
    assert "Kapitel 1" not in abschnitte[0]  # Ueberschrift selbst wird nicht Teil des Koerpers
    assert "Unerwartetes" in abschnitte[1]


def test_text_in_kapitel_teilen_ignoriert_einzelnen_treffer():
    """Nur EINE erkennbare Ueberschrift ist kein Muster (z.B. nur ein
    Titelblatt) - fällt auf die Absatz-Aufteilung zurueck."""
    text = "Kapitel 1: Der Anfang\n\n" + ("Ein Absatz mit Inhalt. " * 100 + "\n\n") * 3
    abschnitte = an.text_in_kapitel_teilen(text)
    assert len(abschnitte) >= 1
    # Die Ueberschrift bleibt als Teil des Fliesstexts erhalten (kein Split).
    assert any("Kapitel 1" in a for a in abschnitte)


def test_text_in_kapitel_teilen_ohne_ueberschriften_gruppiert_nach_wortzahl():
    absatz = "Dies ist ein Beispielabsatz mit einigen Woertern darin, der sich wiederholt. "
    # 12 Absaetze zu je ca. 220 Woertern = ca. 2640 Woerter, deutlich ueber
    # dem 1400-Woerter-Ziel pro Abschnitt (siehe ZIEL_WOERTER_PRO_ABSCHNITT).
    text = "\n\n".join([absatz * 20] * 12)
    abschnitte = an.text_in_kapitel_teilen(text)
    assert len(abschnitte) >= 2
    for abschnitt in abschnitte:
        assert an.woerter(abschnitt) > 0


def test_text_in_kapitel_teilen_leerer_text():
    assert an.text_in_kapitel_teilen("") == []
    assert an.text_in_kapitel_teilen("   \n\n  ") == []


def test_text_in_kapitel_teilen_deckelt_auf_maximum():
    # 40 klar erkennbare Kapitel-Ueberschriften -> muss auf MAX_KAPITEL
    # zusammengefuehrt werden.
    teile = [f"Kapitel {i}: Titel {i}\n\nInhalt von Kapitel {i}. " * 5 for i in range(1, 41)]
    text = "\n\n".join(teile)
    abschnitte = an.text_in_kapitel_teilen(text)
    assert len(abschnitte) <= an.MAX_KAPITEL


def test_kapitel_analyse_parsen_vollstaendige_antwort():
    antwort = (
        "Titel: Der stille Hafen\n"
        "*   Ort: Ein Fischerdorf an der Küste\n"
        "*   Anwesende Figuren: Marek, Lina\n"
        "*   Ereignis: Marek kehrt nach Jahren zurück und trifft Lina wieder.\n"
        "*   Funktion im Spannungsbogen: Exposition\n"
        "*   Stand der Liebeshandlung: Erstes Wiedersehen, unausgesprochene Spannung.\n"
        "*   Zustand am Kapitelende: Beide gehen getrennter Wege, aber nachdenklich.\n"
    )
    analyse = an.kapitel_analyse_parsen(antwort)
    assert analyse.titel == "Der stille Hafen"
    assert analyse.ort == "Ein Fischerdorf an der Küste"
    assert analyse.anwesende_figuren == "Marek, Lina"
    assert "zurück" in analyse.ereignis
    assert analyse.funktion_im_spannungsbogen == "Exposition"
    assert "Wiedersehen" in analyse.stand_der_liebeshandlung
    assert "getrennter Wege" in analyse.zustand_am_kapitelende


def test_kapitel_analyse_parsen_fehlende_felder_werden_platzhalter():
    antwort = "Titel: Nur ein Titel\n*   Ort: Irgendwo\n"
    analyse = an.kapitel_analyse_parsen(antwort)
    assert analyse.ort == "Irgendwo"
    assert analyse.ereignis == "[aus Analyse nicht ersichtlich]"


def test_kapitel_block_bauen_format_matcht_frontend_kapitelplan_parser():
    analyse = an.KapitelAnalyse(
        titel="Der Aufbruch", ort="Hafenstadt", anwesende_figuren="Anna, Jonas",
        ereignis="Sie brechen auf.", funktion_im_spannungsbogen="Exposition",
        stand_der_liebeshandlung="Erstes Kennenlernen.", zustand_am_kapitelende="Beide an Bord.",
    )
    block = an.kapitel_block_bauen(1, analyse, wortzahl_original=1234)
    assert block.startswith("*   **Kapitel eins: Der Aufbruch**")
    assert "    *   Ort: Hafenstadt" in block
    assert "    *   Zielwortzahl: ca. 1250 Wörter." in block  # auf 50 aufgerundet
    assert "    *   Zustand am Kapitelende: Beide an Bord." in block


def test_kapitelplan_block_bauen_nummeriert_fortlaufend():
    analyse = an.KapitelAnalyse("T", "O", "F", "E", "S1", "S2", "Z")
    block = an.kapitelplan_block_bauen([(analyse, 1000), (analyse, 2000)])
    assert "Kapitel eins:" in block
    assert "Kapitel zwei:" in block


def test_geruest_zusammenbauen_fuegt_kapitelplan_vor_offene_punkte_ein():
    synthese = (
        "# STORY-GERUEST\n\n## Rahmen\nJahr: 1888\n\n"
        "## Offene Punkte\nNoch nichts.\n"
    )
    kapitelplan = "*   **Kapitel eins: Test**\n    *   Ort: X"
    ergebnis = an.geruest_zusammenbauen(synthese, kapitelplan)
    assert ergebnis.index("## Kapitelplan") < ergebnis.index("## Offene Punkte")
    assert "*   **Kapitel eins: Test**" in ergebnis
    assert "## Regeln" in ergebnis
    assert ergebnis.index("## Offene Punkte") < ergebnis.index("## Regeln")


def test_geruest_zusammenbauen_ohne_offene_punkte_haengt_hinten_an():
    synthese = "# STORY-GERUEST\n\n## Rahmen\nJahr: 1888\n"
    ergebnis = an.geruest_zusammenbauen(synthese, "*   **Kapitel eins: Test**")
    assert "## Kapitelplan" in ergebnis
    assert ergebnis.index("## Kapitelplan") > ergebnis.index("## Rahmen")
    assert "## Regeln" in ergebnis


def test_geruest_zusammenbauen_ergaenzt_fehlende_literal_marker_im_rahmen():
    """Regression (2026-08-21, Live-Test): die Synthese uebernahm das
    Rahmen-Format der Epoche-Persona woertlich als EINE Kommaliste ('...,
    Jugendfrei, Automatische Fortsetzung (Ein)') statt der fuer
    geruest.py:jugendschutz_stufe_erkennen()/automatische_fortsetzung_
    aktiviert() noetigen eigenen Zeilen - ohne Nachbesserung waere die
    Geschichte faelschlich als "voll" (statt "jugendfrei") explizit
    markiert worden."""
    synthese = (
        "# STORY-GERUEST\n\n## Rahmen\n"
        "Jahr (nicht spezifiziert), Deck des Schiffes, Er-Perspektive, Präsens, dramatisch, "
        "Jugendfrei, Automatische Fortsetzung (Ein)\n\n"
        "## Titel\nSturm über der Meerjungfer\n\n"
        "## Offene Punkte\nNoch nichts.\n"
    )
    ergebnis = an.geruest_zusammenbauen(synthese, "*   **Kapitel eins: Test**")
    assert "Jugendschutz-Stufe: Jugendfrei" in ergebnis
    assert "Automatische Fortsetzung: Ein" in ergebnis
    # Die Ergaenzung muss VOR "## Titel" stehen (also innerhalb von "##
    # Rahmen"), nicht irgendwo im Dokument.
    assert ergebnis.index("Jugendschutz-Stufe: Jugendfrei") < ergebnis.index("## Titel")


def test_geruest_zusammenbauen_laesst_bereits_korrektes_rahmen_unangetastet():
    synthese = (
        "# STORY-GERUEST\n\n## Rahmen\n"
        "*   **Zeitangabe:** Jahr: 1815\n"
        "*   **Jugendschutz-Stufe:** Jugendschutz-Stufe: Angedeutet\n"
        "*   **Automatische Fortsetzung:** Automatische Fortsetzung: Aus\n\n"
        "## Titel\nX\n\n## Offene Punkte\n"
    )
    ergebnis = an.geruest_zusammenbauen(synthese, "*   **Kapitel eins: Test**")
    rahmen_abschnitt = ergebnis[ergebnis.index("## Rahmen"):ergebnis.index("## Titel")]
    # Das Fixture nennt "Jugendschutz-Stufe:" bewusst zweimal (Bold-Label
    # PLUS woertlicher Marker, wie in echten Geruesten ueblich, z.B. "*
    # **Jugendschutz-Stufe:** Jugendschutz-Stufe: Voll") - die Normalisierung
    # darf das NICHT noch ein drittes Mal ergaenzen, da der literale Marker
    # bereits vorhanden ist.
    assert rahmen_abschnitt.count("Jugendschutz-Stufe:") == 2
    assert rahmen_abschnitt.count("Automatische Fortsetzung:") == 2
    assert "Jugendschutz-Stufe: Angedeutet" in rahmen_abschnitt


def test_geruest_zusammenbauen_regeln_enthalten_pflicht_marker():
    ergebnis = an.geruest_zusammenbauen("# STORY-GERUEST\n\n## Rahmen\n", "*   **Kapitel eins: X**")
    assert 'Jugendschutz-Stufe: Voll' in ergebnis
    assert "vierstellig" in ergebnis


def test_grundgeruest_ohne_kapitelplan_entfernt_nur_kapitelplan_abschnitt():
    persona = (
        "Du bist Architekt.\n\n## Ausgabe\n"
        "# STORY-GERUEST\n\n## Rahmen\nJahr, Ort\n\n"
        "## Kapitelplan\nJe Kapitel: ...\n\n"
        "## Offene Punkte\n\n##  Regeln\nBla."
    )
    ergebnis = an._grundgeruest_ohne_kapitelplan(persona)  # noqa: SLF001 - Testzugriff aufs interne Modul
    assert "## Kapitelplan" not in ergebnis
    assert "## Rahmen" in ergebnis
    assert "## Offene Punkte" in ergebnis
    assert "Regeln" not in ergebnis  # war schon vorher durch _grundgeruest() ausgeschlossen


def test_textauszug_bauen_kurzer_text_bleibt_unveraendert():
    text = "Ein kurzer Text mit wenigen Wörtern."
    assert an.textauszug_bauen(text) == text


def test_textauszug_bauen_langer_text_wird_gekuerzt():
    text = " ".join(f"wort{i}" for i in range(2000))
    ergebnis = an.textauszug_bauen(text, woerter_anfang=10, woerter_ende=5)
    assert "wort0" in ergebnis
    assert "wort1999" in ergebnis
    assert "wort1000" not in ergebnis
    assert "[...]" in ergebnis


def test_kapitel_analysen_text_bauen_nummeriert_kapitel():
    analyse = an.KapitelAnalyse("T", "O", "F", "E", "S1", "S2", "Z")
    text = an.kapitel_analysen_text_bauen([(analyse, 100), (analyse, 200)])
    assert "### Kapitel 1" in text
    assert "### Kapitel 2" in text


def test_status_lesen_ohne_datei_liefert_leerzustand(tmp_path):
    status = an.status_lesen(tmp_path)
    assert status["laeuft"] is False
    assert status["log"] == []
    assert status["abgeschlossen"] is False


def test_status_schreiben_und_lesen_roundtrip(tmp_path):
    an.status_schreiben(tmp_path, {"laeuft": True, "phase": "kapitel_analyse", "log": ["x"]})
    status = an.status_lesen(tmp_path)
    assert status["laeuft"] is True
    assert status["phase"] == "kapitel_analyse"
    assert status["log"] == ["x"]


def test_verwaiste_laeufe_zuruecksetzen_setzt_laeuft_false(tmp_path):
    projekt_root = tmp_path / "user" / "Epoche" / "Mein-Projekt"
    an.status_schreiben(projekt_root, {"laeuft": True, "phase": "kapitel_analyse", "log": ["x"], "fehler": None})

    anzahl = an.verwaiste_laeufe_zuruecksetzen(tmp_path)

    assert anzahl == 1
    status = an.status_lesen(projekt_root)
    assert status["laeuft"] is False
    assert status["fehler"]


def test_verwaiste_laeufe_zuruecksetzen_laesst_abgeschlossene_laeufe_unangetastet(tmp_path):
    projekt_root = tmp_path / "user" / "Epoche" / "Mein-Projekt"
    an.status_schreiben(projekt_root, {"laeuft": False, "abgeschlossen": True, "log": [], "fehler": None})

    anzahl = an.verwaiste_laeufe_zuruecksetzen(tmp_path)

    assert anzahl == 0
    status = an.status_lesen(projekt_root)
    assert status["fehler"] is None
