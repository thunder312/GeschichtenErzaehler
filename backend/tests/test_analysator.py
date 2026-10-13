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


def test_ausdrueckliche_kapitel_werden_nicht_auf_30_gestutzt():
    """Stehen die Kapitel ausdruecklich im Text (Chapter/Kapitel), bestimmt
    deren Anzahl die Kapitelzahl - nur absatzweise gebildete Abschnitte
    werden auf MAX_KAPITEL zusammengefuehrt."""
    teile = [f"Kapitel {i}: Titel {i}\n\nInhalt von Kapitel {i}. " * 5 for i in range(1, 41)]
    abschnitte = an.text_in_kapitel_teilen("\n\n".join(teile))
    assert len(abschnitte) == 40


def test_absatz_fallback_deckelt_auf_maximum():
    absatz = "Dies ist ein Beispielabsatz mit einigen Woertern darin. " * 30
    text = "\n\n".join([absatz] * 200)
    assert len(an.text_in_kapitel_teilen(text)) <= an.MAX_KAPITEL


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


def test_analyse_speichern_legt_ordner_an_und_schreibt_text(tmp_path):
    name = an.analyse_speichern(tmp_path, "Mein Titel", "Der Rohtext.")

    assert name == "Mein-Titel.md"
    ziel = tmp_path / "Analyse" / "Mein-Titel.md"
    assert ziel.read_text(encoding="utf-8") == "Der Rohtext."


def test_analyse_speichern_ohne_titel_faellt_auf_import_zurueck(tmp_path):
    name = an.analyse_speichern(tmp_path, "", "Text")
    assert name == "Import.md"


def test_analyse_speichern_haengt_bei_kollision_zaehler_an(tmp_path):
    erster = an.analyse_speichern(tmp_path, "Titel", "Erster Text")
    zweiter = an.analyse_speichern(tmp_path, "Titel", "Zweiter Text")

    assert erster == "Titel.md"
    assert zweiter == "Titel-2.md"
    assert (tmp_path / "Analyse" / "Titel.md").read_text(encoding="utf-8") == "Erster Text"
    assert (tmp_path / "Analyse" / "Titel-2.md").read_text(encoding="utf-8") == "Zweiter Text"


# --- Import-Vorbereitung: Sprache, Fuelltext, Kapitelerkennung --------------

ENGLISCH = (
    "She had not said a word to him since the morning, and he knew that she was angry with his decision. "
    "They walked through the garden with their heads down, but the silence was heavy and he could not "
    "bear it any longer. "
) * 6


def test_sprache_erkennen():
    from app.core.import_bereinigung import sprache_erkennen
    assert sprache_erkennen(ENGLISCH) == "en"
    deutsch = ("Sie hatte ihm seit dem Morgen kein Wort gesagt, und er wusste, dass sie mit seiner Entscheidung "
               "nicht einverstanden war. Sie gingen mit gesenkten Köpfen durch den Garten, aber das Schweigen "
               "war schwer und er konnte es nicht mehr ertragen. ") * 6
    assert sprache_erkennen(deutsch) == "de"
    assert sprache_erkennen("Hallo Welt") == "unbekannt"


def test_vorbereiten_erkennt_englisch_und_englische_kapitelwoerter():
    text = "\n\n".join(f"Chapter {w}\n\n{ENGLISCH}" for w in ("One", "Two", "Three"))
    v = an.vorbereiten(text)
    assert v.sprache == "en"
    assert v.kapitel_quelle == "stichwort"
    assert len(v.abschnitte) == 3


def test_vorbereiten_entfernt_fuelltexte_aber_keine_handlung():
    text = (
        "Title: Der Garten\nRating: T\nSummary: Eine Geschichte.\n\n"
        "Disclaimer: Alle Figuren gehören mir nicht.\n\n"
        "Kapitel 1\n\nEr ging in den Garten.\n\n"
        "A/N: Danke fürs Lesen! Bitte reviewt.\n\n"
        "\"Thanks for coming,\" sagte sie.\n\n"
        "Kapitel 2\n\nSie blieb stehen.\n\n***\n\nAuthor's Note: Nächstes Mal mehr.\n\n"
        "Thanks for reading and for all the reviews!"
    )
    v = an.vorbereiten(text)
    gesamt = "\n".join(v.abschnitte)
    assert "Rating" not in gesamt and "Disclaimer" not in gesamt and "A/N" not in gesamt
    assert "Author's Note" not in gesamt and "Thanks for reading" not in gesamt
    assert "Er ging in den Garten." in gesamt and "Sie blieb stehen." in gesamt
    assert "Thanks for coming" in gesamt  # woertliche Rede bleibt
    # Kopfblock: im Zeilenmodus je Zeile ein Eintrag (Title/Rating/Summary), dazu 4 Absaetze
    assert len(v.entfernt) == 7
    assert not v.abschnitte[1].rstrip().endswith("***")  # Trenner am Kapitelende entfernt
    assert len(v.abschnitte) == 2


def test_vorbereiten_verwirft_reine_fuelltext_kapitel_bei_markdown():
    text = (
        "# Erstes Kapitel\n\nEs begann im Regen.\n\n"
        "# Zweites Kapitel\n\nEs endete im Regen.\n\n"
        "## Author's Note\n\nIch danke allen Lesern."
    )
    v = an.vorbereiten(text)
    assert v.kapitel_quelle == "markdown"
    assert len(v.abschnitte) == 2
    assert v.verworfene_abschnitte == 1


def test_stichwort_kapitel_haben_vorrang_vor_beliebigen_markdown_ueberschriften():
    text = (
        "# Ein Titel\n\nKapitel 1\n\nText eins.\n\n## Zwischentitel\n\nKapitel 2\n\nText zwei.\n\n"
        "Kapitel 3\n\nText drei."
    )
    v = an.vorbereiten(text)
    assert v.kapitel_quelle == "stichwort"
    assert len(v.abschnitte) == 3


def test_prolog_und_zahlwort_kapitel_werden_erkannt():
    text = "Prolog\n\nVorher.\n\nKapitel eins\n\nErstes.\n\nKapitel zwei: Das Ende\n\nLetztes."
    v = an.vorbereiten(text)
    assert v.kapitel_quelle == "stichwort"
    assert len(v.abschnitte) == 3


def test_satz_der_mit_chapter_beginnt_ist_keine_ueberschrift():
    text = ("Chapter three of the old book was long and boring and full of words that nobody read. " * 3
            + "\n\n") * 3
    assert an.vorbereiten(text).kapitel_quelle == "absaetze"


def test_sprachhinweis_nur_bei_englisch():
    assert "Englisch" in an.kapitel_analyse_user("Text", sprache="en")
    assert "Englisch" not in an.kapitel_analyse_user("Text", sprache="de")
    assert "Englisch" in an.synthese_user("Analysen", "Auszug", sprache="en")
    assert "Englisch" in an.epoche_vorschlag_user("Auszug", sprache="en")


def test_vorbereiten_zeilenmodus_pdf_text_ein_absatz_pro_zeile():
    """Aus PDF kopierte Geschichten haben kaum Leerzeilen: jede Zeile ist ein
    Absatz (Regression 'The Sweat of a Gladiator', 18 Kapitel)."""
    text = (
        "The Sweat of a Gladiator\n"
        "A/N: Plot bunny, bitte nett sein.\n"
        "Disclaimer: Nicht meine Figuren.\n"
        "Chapter One\n"
        "Harry rannte durch den Gang.\n"
        "\u201cThanks, Harry,\u201d sagte sie.\n"
        "Er nickte langsam.\n"
        "Chapter Two\n"
        "Authors Postscript: Ein alter Brauch in Japan.\n"
        "Sie lachte laut.\n"
        "Es war vorbei.\n"
    )
    v = an.vorbereiten(text)
    assert len(v.abschnitte) == 2
    assert [e.split(":")[0] for e in v.entfernt] == ["A/N", "Disclaimer", "Authors Postscript"]
    assert "Thanks, Harry" in v.abschnitte[0]
    assert v.abschnitte[0].count("\n\n") == 2  # drei Absaetze, mit Leerzeilen getrennt


# --- Struktur aus bestehender Geschichte: Titel, Rahmen, lange Kapitel, Merkmale ---

def test_kapitel_titel_aus_ueberschrift():
    assert an.kapitel_titel_aus_ueberschrift("Chapter Fifteen: The Final Chapter (Part 1 of 3)") == "The Final Chapter (Part 1 of 3)"
    assert an.kapitel_titel_aus_ueberschrift("Chapter One") == ""
    assert an.kapitel_titel_aus_ueberschrift("## Kapitel 3 - Der Sturm") == "Der Sturm"
    assert an.kapitel_titel_aus_ueberschrift("**Chapter IV: Dusk**") == "Dusk"
    assert an.kapitel_titel_aus_ueberschrift("Prologue") == "Prologue"
    assert an.kapitel_titel_aus_ueberschrift("# Der stille Hafen") == "Der stille Hafen"


def test_vorbereiten_liefert_originaltitel_je_kapitel():
    text = (
        "Chapter One\n\nEs begann.\n\n"
        "Chapter Two: The Storm\n\nDann kam der Sturm.\n\n"
        "Chapter Three: Home\n\nEnde."
    )
    v = an.vorbereiten(text)
    assert v.titel == ["", "The Storm", "Home"]
    assert len(v.titel) == len(v.abschnitte)


def test_kapitel_block_entfernt_sternchen_aus_dem_titel():
    """Regression 2026-10-13: '**Kapitel eins: *Titel***' liess sich im Editor nicht in Karten zerlegen."""
    analyse = an.KapitelAnalyse("*Ron's Vergiftung*", "Krankenzimmer", "Harry", "E", "Exposition", "Begegnung", "Z")
    block = an.kapitel_block_bauen(1, analyse, 3000)
    erste_zeile = block.splitlines()[0]
    assert erste_zeile == "*   **Kapitel eins: Ron's Vergiftung**"


def test_kapitel_analyse_parsen_titel_ohne_markdown_und_neue_felder():
    antwort = (
        "Titel: *Gefahr im Sturm*\n"
        "*   Vergangene Zeit: zwei Tage später\n"
        "*   Ort: Leuchtturm\n"
        "*   Anwesende Figuren: Eleanor\n"
        "*   Ereignis: Eleanor zündet das Licht an.\n"
        "*   Funktion im Spannungsbogen: Exposition\n"
        "*   Stand der Liebeshandlung: Keine Liebeshandlung\n"
        "*   Zustand am Kapitelende: Draußen.\n"
        "*   Explizitheit: keine\n"
    )
    a = an.kapitel_analyse_parsen(antwort)
    assert a.titel == "Gefahr im Sturm"
    assert a.vergangene_zeit == "zwei Tage später"
    assert a.explizitheit == "keine"


def test_kapitel_block_hat_vergangene_zeit_erst_ab_kapitel_zwei():
    analyse = an.KapitelAnalyse("T", "O", "F", "E", "S1", "S2", "Z", vergangene_zeit="am nächsten Morgen")
    eins = an.kapitel_block_bauen(1, analyse, 1000)
    zwei = an.kapitel_block_bauen(2, analyse, 1000)
    assert "    *   Vergangene Zeit: \n" in eins
    assert "    *   Vergangene Zeit: am nächsten Morgen\n" in zwei


def test_funktion_und_liebesstufe_werden_normalisiert():
    assert an.funktion_normalisieren("Wendepunkt - die Handlung erreicht einen kritischen Punkt") == "Höhepunkt/Peripetie"
    assert an.funktion_normalisieren("exposition und Einleitung") == "Exposition"
    assert an.funktion_normalisieren("Eskalation der Lage") == "Steigende Handlung"
    assert an.funktion_normalisieren("etwas ganz anderes") == "etwas ganz anderes"
    assert an.liebesstufe_normalisieren("annaeherung (erste Vertrautheit)") == "Annäherung (erste Vertrautheit)"
    assert an.liebesstufe_normalisieren("Kuss (im Regen)") == "Kuss (im Regen)"
    assert an.liebesstufe_normalisieren("Harry und Hermione stehen sich nah") == "Harry und Hermione stehen sich nah"


def test_abschnitt_in_teile_und_zusammenfuehren():
    absatz = "Wort " * 400
    text = "\n\n".join([absatz] * 14)  # 5600 Woerter
    assert an.abschnitt_in_teile(absatz) == [absatz]
    teile = an.abschnitt_in_teile(text, max_woerter=2000)
    assert 3 <= len(teile) <= 4
    assert sum(an.woerter(t) for t in teile) == an.woerter(text)  # nichts geht verloren

    a = an.KapitelAnalyse("Titel", "Haus", "Anna, Ben", "Erstens.", "Exposition", "Begegnung", "Draußen", "kein", "keine")
    b = an.KapitelAnalyse("Anderer", "Haus, Garten", "Ben, Cora", "Zweitens.", "Höhepunkt/Peripetie", "Kuss", "Im Bett", "x", "explizit")
    z = an.analysen_zusammenfuehren([a, b])
    assert z.titel == "Titel"
    assert z.ort == "Haus, Garten"
    assert z.anwesende_figuren == "Anna, Ben, Cora"
    assert z.ereignis == "Erstens. Zweitens."
    assert z.funktion_im_spannungsbogen == "Höhepunkt/Peripetie"
    assert z.stand_der_liebeshandlung == "Kuss"
    assert z.explizitheit == "explizit"
    assert an.analysen_zusammenfuehren([a]) is a


def test_kapitel_analyse_user_nennt_originaltitel_teil_und_satzzahl():
    u = an.kapitel_analyse_user("Wort " * 3200, "en", index=17, gesamt=18, originaltitel="The Final Chapter", teil=(2, 3))
    assert "Kapitel 17 von 18" in u and "TEIL 2 von 3" in u
    assert "ORIGINALTITEL" in u and "The Final Chapter" in u and "übersetzt" in u
    assert "etwa 4 Sätzen" in u  # 3200 Woerter -> 2 + 3200 // 1500
    ohne = an.kapitel_analyse_user("Text", "de")
    assert "keinen Originaltitel" in ohne


# Reale Rahmen-Ausgabe der Synthese (Harry-Potter-Epoche): leere Bullets plus EINE Semikolon-Zeile
REALER_RAHMEN = (
    "# STORY-GERUEST\n\n## Rahmen\n"
    "*   **Zeitangabe:** \n*   **Ort:** \n*   **Erzählperspektive:** Dritte Person\n"
    "*   **Tempus:** Vergangenheitsform\n*   **Tonlage:** \n"
    "*   **Jugendschutz-Stufe:** Jugendschutz-Stufe: Voll\n"
    "*   Jahr: unbekannt; Ort: Hogwarts und London; Jahreszeit/Tageszeit: nicht spezifiziert; "
    "Erzählperspektive: Dritte Person (auktorial); Tempus: Präsens; Tonlage: humorvoll-erotisch.\n"
    "*   Jugendschutz-Stufe: Voll\n*   Automatische Fortsetzung: Aus\n\n"
    "## Titel\nEin Titel\n"
)


def test_rahmen_felder_lesen_aus_gemischter_darstellung():
    block = REALER_RAHMEN.split("## Rahmen\n")[1].split("\n## Titel")[0]
    felder = an.rahmen_felder_lesen(block)
    assert felder["ort"] == "Hogwarts und London"
    assert felder["perspektive"] == "Dritte Person"
    assert felder["tonlage"].startswith("humorvoll")
    assert "zeitangabe" not in felder  # "unbekannt" zaehlt als leer
    assert "jahreszeit" not in felder  # "nicht spezifiziert" zaehlt als leer


def test_rahmen_aufbauen_zeitangabe_nur_jahr_und_fakten_gewinnen():
    fakten = {"jugendschutz": "Voll", "perspektive": "dritte Person", "tempus": "Präteritum"}
    ergebnis = an.rahmen_aufbauen(REALER_RAHMEN, fakten)
    rahmen = ergebnis.split("## Rahmen\n")[1].split("\n## Titel")[0]
    zeilen = rahmen.strip().splitlines()
    assert zeilen[0] == "*   **Zeitangabe:**"  # leer statt "unbekannt"
    assert "*   **Ort:** Hogwarts und London" in zeilen
    assert "*   **Tempus:** Vergangenheitsform" in zeilen  # Zaehlung (Praeteritum) schlaegt KI-"Praesens"
    assert "*   **Jugendschutz-Stufe:** Jugendschutz-Stufe: Voll" in zeilen
    assert "*   **Automatische Fortsetzung:** Automatische Fortsetzung: Aus" in zeilen
    assert rahmen.count("Jugendschutz-Stufe:") == 2  # genau EIN Eintrag, nicht doppelt
    assert "unbekannt" not in rahmen and "Jahreszeit" not in rahmen
    assert "## Titel\nEin Titel" in ergebnis  # Rest bleibt unangetastet
    from app.core import geruest as g
    assert g.jugendschutz_stufe_erkennen(ergebnis) == "voll"


def test_rahmen_aufbauen_uebernimmt_vierstelliges_jahr_und_korrigiert_perspektive():
    geruest = (
        "## Rahmen\nJahr: um 1815 herum, Ort: Bath, Jahreszeit: Frühling, Erzählperspektive: Dritte Person, "
        "Tempus: Präteritum, Tonlage: ironisch, Jugendschutz-Stufe: Voll, Automatische Fortsetzung: Ein\n\n## Titel\nX\n"
    )
    fakten = {"jugendschutz": "Jugendfrei", "perspektive": "erste Person", "tempus": None}
    ergebnis = an.rahmen_aufbauen(geruest, fakten)
    assert "*   **Zeitangabe:** 1815" in ergebnis
    assert "*   **Jahreszeit:** Frühling" in ergebnis
    assert "*   **Erzählperspektive:** Ich-Erzähler (erste Person)" in ergebnis
    assert "*   **Tempus:** Vergangenheitsform" in ergebnis
    assert "Jugendschutz-Stufe: Jugendfrei" in ergebnis
    assert "Automatische Fortsetzung: Ein" in ergebnis
    from app.core import geruest as g
    assert g.jahr_erkennen(ergebnis) == "1815"


def test_geruest_zusammenbauen_mit_fakten_baut_rahmen_neu():
    fakten = {"jugendschutz": "Angedeutet", "perspektive": None, "tempus": None}
    ergebnis = an.geruest_zusammenbauen(REALER_RAHMEN, "*   **Kapitel eins: Test**", fakten)
    assert "Jugendschutz-Stufe: Angedeutet" in ergebnis
    assert "## Kapitelplan" in ergebnis


def test_fakten_text_fuer_die_synthese():
    assert an.fakten_text(None) == ""
    t = an.synthese_user("Analysen", "Auszug", "de", {"jugendschutz": "Voll", "perspektive": "dritte Person", "tempus": "Präteritum"})
    assert "Feststehende Fakten" in t and "Jugendschutz-Stufe: Voll" in t and "Erzählperspektive: dritte Person" in t


# --- app/core/import_merkmale.py ----------------------------------------------

def test_erzaehlperspektive_und_tempus_erkennen():
    from app.core import import_merkmale as m
    dritte = ("He walked to the window and she followed him. His hands were cold and her voice was low, "
              "and they said nothing. He had seen her before, and he knew she was afraid. ") * 8
    erste = ("I walked to the window and I knew that my hands were cold. She followed me and I said nothing, "
             "because I had seen her before and I was afraid. ") * 8
    assert m.erzaehlperspektive_erkennen(dritte) == "dritte Person"
    assert m.erzaehlperspektive_erkennen(erste) == "erste Person"
    assert m.erzaehlperspektive_erkennen("zu kurz") is None
    # Ich-Pronomen in woertlicher Rede zaehlen NICHT zur Erzaehlstimme
    mit_rede = dritte + ' "I think I know what I want," she said. "I do." ' * 10
    assert m.erzaehlperspektive_erkennen(mit_rede) == "dritte Person"

    vergangen = "He was tired and she had been angry. He said that they were late. " * 12
    gegenwart = "He is tired and she has been angry. He says that they are late. " * 12
    assert m.tempus_erkennen(vergangen) == "Präteritum"
    assert m.tempus_erkennen(gegenwart) == "Präsens"
    assert m.tempus_erkennen("kurz") is None


def test_explizitheit_bewerten_und_hoechste_stufe():
    from app.core import import_merkmale as m
    harmlos = "Sie gingen durch den Garten und redeten über das Wetter und die Ernte. " * 50
    zaertlich = ("Er küsste sie sanft. " * 7) + harmlos
    explizit = "He kissed her and his cock was hard. She moaned as he thrust, and she came, an orgasm that " * 3 + "x " * 300
    assert m.explizitheit_bewerten(harmlos) == "keine"
    assert m.explizitheit_bewerten(zaertlich) == "angedeutet"
    assert m.explizitheit_bewerten(explizit) == "explizit"
    assert m.hoechste_stufe(["keine", "explizit", "angedeutet"]) == "explizit"
    assert m.hoechste_stufe([]) == "keine"
    assert m.jugendschutz_aus_stufe("keine") == "Jugendfrei"
    assert m.jugendschutz_aus_stufe("angedeutet") == "Angedeutet"
    assert m.jugendschutz_aus_stufe("explizit") == "Voll"


def test_figuren_bereinigen_entfernt_dopplungen_und_kurzformen():
    text = "Susan Bones, Harry Potter, Hermione Granger, Harry, Hermione, Luna, Susan, Ron, harry potter"
    assert an.figuren_bereinigen(text) == "Susan Bones, Harry Potter, Hermione Granger, Luna, Ron"
    assert an.figuren_bereinigen("[aus Analyse nicht ersichtlich]") == "[aus Analyse nicht ersichtlich]"


def test_liebesstufe_ohne_anweisungstext_aus_der_persona():
    roh = "Körperliche Erfüllung - gefolgt von einem kurzen Satz in Klammern. (Sie lieben sich)"
    assert an.liebesstufe_normalisieren(roh) == "Körperliche Erfüllung (Sie lieben sich)"


def test_titel_ohne_pdf_artefakte():
    assert an.kapitel_titel_aus_ueberschrift("Chapter Sixteen: The Final Chapter (2 of 3 �?)") == "The Final Chapter (2 of 3)"


def test_vergangene_zeit_ohne_platzhalter_im_kapitelplan():
    fehlt = an.KapitelAnalyse("T", "O", "F", "E", "S1", "S2", "Z", vergangene_zeit="[aus Analyse nicht ersichtlich]")
    block = an.kapitel_block_bauen(2, fehlt, 1000)
    assert "Vergangene Zeit: \n" in block


def test_rahmen_perspektive_beginnt_gross():
    geruest = "## Rahmen\nErzählperspektive: dritte Person\n\n## Titel\nX\n"
    ergebnis = an.rahmen_aufbauen(geruest, {"jugendschutz": "Voll", "perspektive": "dritte Person", "tempus": None})
    assert "*   **Erzählperspektive:** Dritte Person" in ergebnis
