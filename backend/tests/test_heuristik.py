from app.core import heuristik as h


def test_sprachdrift_pruefen_erkennt_hohen_englischen_anteil():
    text = " ".join(["the", "and", "was", "were", "with"] * 10 + ["Baum"] * 5)
    findings = h.sprachdrift_pruefen(text)
    assert len(findings) == 1
    assert findings[0].code == "sprachdrift"


def test_sprachdrift_pruefen_kein_fund_bei_deutschem_text():
    text = "Der Wald war still und die Voegel sangen leise im Wind."
    assert h.sprachdrift_pruefen(text) == []


def test_sprachdrift_lokal_pruefen_erkennt_einzelnen_satzfetzen_in_langem_kapitel():
    """Regression: ein einzelner englischer Satz mitten in einem sonst
    langen deutschen Kapitel faellt bei sprachdrift_pruefen()s Prozent-
    Schwelle nicht auf (siehe 'Diesmal because of love.'-Vorfall)."""
    lange_umgebung = "Der Baum stand still im Wind und schwieg. " * 100
    text = lange_umgebung + "Diesmal because of love. " + lange_umgebung
    assert h.sprachdrift_pruefen(text) == []
    findings = h.sprachdrift_lokal_pruefen(text)
    assert len(findings) == 1
    assert findings[0].code == "sprachdrift_lokal"
    assert "because" in findings[0].meldung


def test_sprachdrift_lokal_pruefen_ignoriert_deutsche_woerter_was_und_her():
    text = "Sie fragte, was er meinte, und er kam sofort her zu ihr."
    assert h.sprachdrift_lokal_pruefen(text) == []


def test_sprachdrift_lokal_pruefen_kein_fund_bei_deutschem_text():
    text = "Der Wald war still und die Voegel sangen leise im Wind."
    assert h.sprachdrift_lokal_pruefen(text) == []


def test_erzaehlperspektive_ignoriert_ich_in_woertlicher_rede():
    geruest = "Erzaehlperspektive: Dritte Person"
    text = 'Sie sagte: „Ich gehe jetzt nach Hause, mein Freund wartet."'
    assert h.erzaehlperspektive_pruefen(text, geruest) == []


def test_erzaehlperspektive_erkennt_drift_ausserhalb_der_rede():
    geruest = "Erzaehlperspektive: Dritte Person"
    text = "Ich ging langsam durch meine Strasse und dachte an mein Zuhause."
    findings = h.erzaehlperspektive_pruefen(text, geruest)
    assert len(findings) == 1
    assert findings[0].code == "ich_perspektive"


def test_erzaehlperspektive_ohne_dritte_person_vorgabe_kein_check():
    text = "Ich ging langsam durch meine Strasse."
    assert h.erzaehlperspektive_pruefen(text, "keine Vorgabe im Geruest") == []


def test_anredeform_erkennt_mischung_in_dialog():
    text = 'Er fragte: „Kommst du mit?" Sie antwortete: „Wollen Sie das wirklich wissen?"'
    findings = h.anredeform_pruefen(text)
    assert len(findings) == 1
    assert findings[0].code == "anredeform"


def test_anredeform_ignoriert_sie_ausserhalb_der_rede():
    text = "Sie ging durch den Wald und du dachte an nichts anderes als an den Weg zurueck."
    assert h.anredeform_pruefen(text) == []


def test_fuehrende_markdown_ueberschrift_entfernen_erkennt_doppelte_angabe():
    text = "## Kapitel 2\n\nKapitel zwei: Der Blick auf die Baustelle\n\nErster Absatz."
    bereinigt, findings = h.fuehrende_markdown_ueberschrift_entfernen(text)
    assert bereinigt == "Kapitel zwei: Der Blick auf die Baustelle\n\nErster Absatz."
    assert len(findings) == 1
    assert findings[0].code == "markdown_ueberschrift"


def test_fuehrende_markdown_ueberschrift_entfernen_ohne_markdown_unveraendert():
    text = "Kapitel eins: Ankunft\n\nEin einzelner Absatz ohne Markdown."
    bereinigt, findings = h.fuehrende_markdown_ueberschrift_entfernen(text)
    assert bereinigt == text
    assert findings == []


def test_kapitelueberschrift_sicherstellen_ergaenzt_fehlende_ueberschrift():
    kapitel_block = (
        "*   **Kapitel eins: Die letzte Chance**\n"
        "    *   Ort: Zauberei-Ministerium\n"
        "    *   Zielwortzahl: ca. 1500 Wörter."
    )
    text = "Das Zauberei-Ministerium war an diesem Sommermorgen so geschäftig wie eh und je."
    ergaenzt, findings = h.kapitelueberschrift_sicherstellen(text, kapitel_block)
    assert ergaenzt == "Kapitel eins: Die letzte Chance\n\n" + text
    assert len(findings) == 1
    assert findings[0].code == "kapitelueberschrift_fehlt"


def test_kapitelueberschrift_sicherstellen_laesst_vorhandene_ueberschrift_unangetastet():
    kapitel_block = "*   **Kapitel vier: Das soll lecker sein?**\n    *   Ort: Daniels Labor"
    # Vorhandene Ueberschrift in Markdown-Fettdruck statt reinem Text (wie
    # beim realen Vorfall) - gilt trotzdem als "vorhanden", wird NICHT
    # nochmal davorgesetzt.
    text = "**Kapitel vier: Das soll lecker sein?**\n\nPünktlich erschien Hermine um 8 Uhr im Labor."
    ergaenzt, findings = h.kapitelueberschrift_sicherstellen(text, kapitel_block)
    assert ergaenzt == text
    assert findings == []


def test_kapitelueberschrift_sicherstellen_ohne_kapitelplan_block_unveraendert():
    text = "Ein Kapitel ohne jede Ueberschrift und ohne bekannten Kapitelplan-Block."
    ergaenzt, findings = h.kapitelueberschrift_sicherstellen(text, None)
    assert ergaenzt == text
    assert findings == []


def test_kapitel_neustart_abschneiden_erkennt_doppelte_ueberschrift():
    text = (
        "Kapitel eins: Ankunft\n\nErster Absatz.\n\n"
        "Kapitel eins: Ankunft\n\nZweiter, widerspruechlicher Durchlauf."
    )
    gekuerzt, findings = h.kapitel_neustart_abschneiden(text)
    assert "Zweiter, widerspruechlicher" not in gekuerzt
    assert len(findings) == 1
    assert findings[0].code == "kapitel_neustart"


def test_kapitel_neustart_abschneiden_ohne_wiederholung_unveraendert():
    text = "Kapitel eins: Ankunft\n\nEin einzelner Absatz ohne Wiederholung."
    gekuerzt, findings = h.kapitel_neustart_abschneiden(text)
    assert gekuerzt == text
    assert findings == []


def test_vorzeitige_kapitelende_abschneiden_bei_substanziellem_rest():
    rest = " ".join(["weiter"] * 60)
    text = f"Das Kapitel endete damit, dass sie schwiegen. Zwei Tage spaeter: {rest}."
    gekuerzt, findings = h.vorzeitige_kapitelende_abschneiden(text)
    assert "Zwei Tage spaeter" not in gekuerzt
    assert len(findings) == 1


def test_vorzeitige_kapitelende_abschneiden_bei_kurzem_rest_bleibt_text():
    text = "Das Kapitel endete damit, dass sie schwiegen. Ein letzter Blick."
    gekuerzt, findings = h.vorzeitige_kapitelende_abschneiden(text)
    assert gekuerzt == text
    assert findings == []


def test_fuehrende_duplikate_entfernen_erkennt_wiederholten_absatz():
    bisheriger_text = "Erster Absatz.\n\nZweiter Absatz, der Vorgaenger endet hier."
    fortsetzung = "Zweiter Absatz, der Vorgaenger endet hier.\n\nDritter, neuer Absatz."
    bereinigt, findings = h.fuehrende_duplikate_entfernen(bisheriger_text, fortsetzung)
    assert bereinigt == "Dritter, neuer Absatz."
    assert len(findings) == 1


def test_interne_wiederholung_abschneiden_erkennt_schleife():
    block = "Er kuesste sie sanft.\n\nSie stoehnte leise auf."
    text = "Einleitender Absatz, der nur einmal vorkommt.\n\n" + "\n\n".join([block] * 4)
    gekuerzt, findings = h.interne_wiederholung_abschneiden(text)
    assert gekuerzt == "Einleitender Absatz, der nur einmal vorkommt.\n\n" + block
    assert len(findings) == 1
    assert findings[0].code == "interne_wiederholung"


def test_interne_wiederholung_abschneiden_ohne_schleife_unveraendert():
    text = "Erster Absatz.\n\nZweiter, ganz anderer Absatz.\n\nDritter Absatz zum Schluss."
    gekuerzt, findings = h.interne_wiederholung_abschneiden(text)
    assert gekuerzt == text
    assert findings == []


def test_interne_wiederholung_abschneiden_zweimalige_wiederholung_kein_fund():
    # Zwei Kopien allein sind noch kein zuverlaessiges Schleifen-Signal -
    # z.B. ein bewusst wiederholter Refrain im Text.
    block = "Ein wiederkehrender Refrain."
    text = "Auftakt.\n\n" + "\n\n".join([block] * 2)
    gekuerzt, findings = h.interne_wiederholung_abschneiden(text)
    assert gekuerzt == text
    assert findings == []


def test_wiederholten_absatzblock_ausschneiden_erkennt_nicht_angrenzende_wiederholung():
    """Regression: interne_wiederholung_abschneiden() vergleicht nur den
    UNMITTELBAR naechsten Absatzblock (j = i + k) - liegt zwischen zwei
    (fast) identischen Bloecken ein andersformuliertes Zwischenstueck (wie
    beim realen Vorfall in Kapitel 4 von "Das-Echo-der-Verpflichtung-Ein-
    Geheimnis-in-Winterbottom-Hall"), findet interne_wiederholung_
    abschneiden() nichts. wiederholten_absatzblock_ausschneiden() muss den
    Fall trotzdem erkennen und NUR den redundanten Mittelteil entfernen,
    der Text danach (hier: der Schlussabsatz) muss erhalten bleiben."""
    block = (
        "Marcus fragte sie leise, was das Dokument bedeute, und wartete auf "
        "ihre Antwort mit angehaltenem Atem.\n\n"
        "Julia erklaerte ihm die Zusammenhaenge, so gut sie es aus den alten "
        "Papieren herauslesen konnte, ihre Stimme leicht zitternd.\n\n"
        "Er nickte langsam und wandte sich zum Fenster, um seine Fassung "
        "wiederzufinden, bevor er antwortete."
    )
    zwischenstueck = (
        "Ein Diener klopfte kurz an die Tuer, trat aber nicht ein, sondern "
        "entfernte sich wieder auf leisen Sohlen den Flur hinunter."
    )
    text = (
        "Einleitender Absatz, der nur einmal vorkommt.\n\n"
        + block + "\n\n" + zwischenstueck + "\n\n" + block
        + "\n\nAbschliessender Absatz, der unbedingt erhalten bleiben muss."
    )
    gekuerzt, findings = h.wiederholten_absatzblock_ausschneiden(text)
    assert len(findings) == 1
    assert findings[0].code == "wiederholter_absatzblock"
    assert gekuerzt.startswith("Einleitender Absatz, der nur einmal vorkommt.\n\n" + block)
    assert gekuerzt.endswith("Abschliessender Absatz, der unbedingt erhalten bleiben muss.")
    assert zwischenstueck not in gekuerzt
    assert gekuerzt.count("Marcus fragte sie leise") == 1


def test_wiederholten_absatzblock_ausschneiden_ohne_wiederholung_unveraendert():
    text = "Erster Absatz.\n\nZweiter, ganz anderer Absatz.\n\nDritter Absatz zum Schluss."
    gekuerzt, findings = h.wiederholten_absatzblock_ausschneiden(text)
    assert gekuerzt == text
    assert findings == []


def test_wiederholten_absatzblock_ausschneiden_ignoriert_kurzen_refrain():
    # Ein einzelner, kurzer wiederkehrender Satz (< min_fenster Absaetze)
    # bleibt bewusst unangetastet - siehe interne_wiederholung_abschneiden()-
    # Pendant-Test: kann ein gewollter Stil-Refrain sein.
    refrain = "Der Punkt ohne Wiederkehr war erreicht."
    text = "Auftakt.\n\n" + refrain + "\n\nMittelteil.\n\n" + refrain + "\n\nSchluss."
    gekuerzt, findings = h.wiederholten_absatzblock_ausschneiden(text)
    assert gekuerzt == text
    assert findings == []


def test_wiederholten_absatzblock_ausschneiden_erkennt_kurzen_2absatz_block():
    """Regression: ein KURZER 2-Absatz-Dialogschnipsel (z.B. Frage-und-
    Reaktions-Zeile), der spaeter im Kapitel noch einmal (fast) wortgleich
    auftaucht, fiel bei min_fenster=3 durchs Raster - siehe Docstring von
    wiederholten_absatzblock_ausschneiden(). min_fenster=2 muss ihn jetzt
    erfassen, waehrend ein einzelner 1-Absatz-Refrain weiterhin ignoriert
    wird (siehe test_..._ignoriert_kurzen_refrain direkt darueber)."""
    block = (
        "Marcus blickte von dem vergilbten Dokument auf, sein Gesicht war "
        "blass geworden.\n\n"
        "„Was bedeutet das?“, fragte er leise, die Stimme kaum mehr als ein "
        "Flüstern."
    )
    zwischenstueck = (
        "Julia schwieg einen Moment und sah aus dem Fenster, bevor sie "
        "wieder zu den Papieren griff."
    )
    text = (
        "Einleitender Absatz, der nur einmal vorkommt.\n\n"
        + block + "\n\n" + zwischenstueck + "\n\n" + block
        + "\n\nAbschliessender Absatz, der unbedingt erhalten bleiben muss."
    )
    gekuerzt, findings = h.wiederholten_absatzblock_ausschneiden(text)
    assert len(findings) == 1
    assert findings[0].code == "wiederholter_absatzblock"
    assert gekuerzt.count("Marcus blickte von dem vergilbten Dokument auf") == 1
    assert gekuerzt.endswith("Abschliessender Absatz, der unbedingt erhalten bleiben muss.")


def test_wiederholten_absatzblock_ausschneiden_kapitel4_realfall():
    """End-to-End gegen den (gekuerzten) Originaltext von Kapitel 4 aus
    "Das-Echo-der-Verpflichtung-Ein-Geheimnis-in-Winterbottom-Hall" (Live-
    Vorfall vom 2026-08-10) - muss den bekannten Duplikat-Block entfernen,
    ohne den Schlussteil (neue, einmalige Liebesgestaendnis-Szene) zu
    verlieren."""
    text = (
        "Marcus starrte sie an, sein Gesicht war blass geworden. „Was meinen Sie?“\n\n"
        "Julia blickte zu ihm auf, ihre Augen waren voller Sorge. „Es scheint, als ob "
        "Ihr Vorfahre einen Handel geschlossen hat, der nicht nur finanziell, sondern "
        "auch emotional belastet war. Es gibt Andeutungen von Verrat und Verlust.“\n\n"
        "Finch nickte langsam. „Genau das ist es, was ich Ihnen zeigen wollte.“\n\n"
        "Marcus spürte, wie ihm übel wurde. Er wandte sich ab und ging zum Fenster, "
        "wo er in den dunklen Wald hinausstarrte.\n\n"
        "Julia legte sanft eine Hand auf seinen Arm. „Marcus, wir müssen die Wahrheit "
        "herausfinden. Egal, wie schmerzhaft sie ist.“\n\n"
        "Er drehte sich zu ihr um, seine Augen waren feucht vor unvergossenen Tränen. "
        "„Warum? Warum sollte ich etwas wissen wollen, das mich nur noch mehr leiden "
        "lässt?“\n\n"
        "Julia nahm vorsichtig eines der Papiere und begann zu lesen. Ihre Stimme war "
        "ruhig, aber ihre Hände zitterten.\n\n"
        "Marcus starrte sie an, sein Gesicht war blass geworden. „Was für eine "
        "Schuld?“\n\n"
        "Julia blickte zu ihm auf, ihre Augen waren voller Sorge. „Es scheint, als ob "
        "jemand betrogen wurde. Jemand, den Ihr Vorfahre geliebt hat.“\n\n"
        "Marcus spürte, wie sich ein Knoten in seinem Magen bildete. Er wandte sich ab "
        "und ging zum Fenster, wo er in den dunklen Wald hinausstarrte.\n\n"
        "Julia legte sanft eine Hand auf seinen Arm. „Marcus, wir müssen die Wahrheit "
        "herausfinden. Egal, wie schmerzhaft sie ist.“\n\n"
        "Er drehte sich zu ihr um, seine Augen waren feucht vor unvergossenen Tränen. "
        "„Warum? Warum sollte ich etwas wissen wollen, das mich nur noch mehr leiden "
        "lässt?“\n\n"
        "Finch lächelte leicht und deutete auf einen Stapel weiterer Papiere auf dem "
        "Schreibtisch. „Dort finden Sie alles, was Sie brauchen.“\n\n"
        "Die Stunden vergingen, während Marcus und Julia die vergilbten Papiere "
        "durchforsteten.\n\n"
        "„Gut“, flüsterte er. „Dann lass uns beginnen.“"
    )
    gekuerzt, findings = h.wiederholten_absatzblock_ausschneiden(text)
    assert len(findings) == 1
    assert gekuerzt.count("Finch lächelte leicht und deutete auf einen Stapel") == 1
    assert gekuerzt.count("Julia legte sanft eine Hand auf seinen Arm") == 1
    assert "Gut“, flüsterte er. „Dann lass uns beginnen." in gekuerzt
    assert "Die Stunden vergingen" in gekuerzt


def test_explizitheit_pruefen_nur_relevant_wenn_nicht_voll():
    text = "Eine Szene mit Penetration und Orgasmus."
    assert h.explizitheit_pruefen(text, "voll") == []
    findings = h.explizitheit_pruefen(text, "jugendfrei")
    assert len(findings) == 1
    assert "penetration" in findings[0].meldung.lower()


def test_ausweichformulierungen_pruefen():
    assert h.ausweichformulierungen_pruefen("Sie fanden die Sprache des Samens.")
    assert h.ausweichformulierungen_pruefen("Ein ganz normaler Satz.") == []


def test_hunspell_unbekannte_woerter_nutzt_exec_fn():
    def gefaelschte_ausfuehrung(cmd, stdin_text):
        assert cmd[0] == "hunspell"
        return 0, "Schmettelving\nab\nHaus\n", ""

    ergebnis = h.hunspell_unbekannte_woerter("irrelevanter Text", exec_fn=gefaelschte_ausfuehrung)
    assert ergebnis == ["Haus", "Schmettelving"]  # "ab" faellt wegen Laenge < 3 raus


def test_hunspell_unbekannte_woerter_liefert_none_bei_fehlendem_tool():
    def wirft_fehlend(cmd, stdin_text):
        raise FileNotFoundError()

    assert h.hunspell_unbekannte_woerter("Text", exec_fn=wirft_fehlend) is None


def test_wort_position_finden_liefert_erste_fundstelle():
    text = "Der Baum stand am Rand. Ein Schmettelving flog vorbei zum Schmettelving."
    start, end = h.wort_position_finden(text, "Schmettelving")
    assert text[start:end] == "Schmettelving"
    assert start == text.index("Schmettelving")


def test_wort_position_finden_nur_als_eigenes_wort():
    text = "Der Baumstamm lag im Wald, kein Baum weit und breit."
    start, end = h.wort_position_finden(text, "Baum")
    assert text[start:end] == "Baum"
    assert text[:start] == "Der Baumstamm lag im Wald, kein "


def test_wort_position_finden_ohne_treffer():
    assert h.wort_position_finden("Der Baum stand still.", "Schmettelving") is None
