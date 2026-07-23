from app.core import heuristik as h


def test_sprachdrift_pruefen_erkennt_hohen_englischen_anteil():
    text = " ".join(["the", "and", "was", "were", "with"] * 10 + ["Baum"] * 5)
    findings = h.sprachdrift_pruefen(text)
    assert len(findings) == 1
    assert findings[0].code == "sprachdrift"


def test_sprachdrift_pruefen_kein_fund_bei_deutschem_text():
    text = "Der Wald war still und die Voegel sangen leise im Wind."
    assert h.sprachdrift_pruefen(text) == []


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
