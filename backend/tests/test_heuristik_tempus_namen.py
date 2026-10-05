from app.api import pipeline
from app.core import heuristik as h

GERUEST = (
    "# STORY-GERUEST\n\n## Figuren\n"
    "*   **Nina:** Bauerntochter\n*   **Herzog Daniel:** verwaltet das Herzogtum\n"
)
STAND = "Nina arbeitet in der Küche bei Martha, der Köchin."


# --- Tempus in wörtlicher Rede ---------------------------------------------

def test_tempus_rede_meldet_praeteritum_in_der_rede():
    text = 'Sie sah ihn an. „Ich hoffte, dass ihr beide glücklich werdet.“'

    findings = h.tempus_in_rede_pruefen(text)

    assert [f.code for f in findings] == ["tempus_rede"]
    assert "Ich hoffte" in findings[0].meldung


def test_tempus_rede_meldet_starkes_praeteritum():
    # Nur "Pronomen + Verb" wird erkannt; invertierte Stellung ("Dann ging er")
    # bleibt bewusst unerkannt (siehe Docstring von tempus_in_rede_pruefen).
    findings = h.tempus_in_rede_pruefen('„Dann ging er fort und ich blieb allein.“')

    assert len(findings) == 1
    assert "ich blieb" in findings[0].meldung
    assert "ging" not in findings[0].meldung


def test_tempus_rede_erlaubt_hilfs_und_modalverben_und_konjunktiv():
    text = (
        '„Ich war müde, er hatte Hunger, sie wollte gehen und wir konnten nicht bleiben. '
        'Ich möchte wissen, was es wäre, wenn ich hätte bleiben können.“'
    )

    assert h.tempus_in_rede_pruefen(text) == []


def test_tempus_rede_erlaubt_praesens_formen_auf_te():
    text = '„Ich warte hier, ich bitte dich, ich antworte dir morgen. Ich erbitte Euren Rat.“'

    assert h.tempus_in_rede_pruefen(text) == []


def test_tempus_rede_ignoriert_erzaehltext_im_praeteritum():
    text = 'Er sah sie an und sie lächelte. Dann ging er fort, und sie hoffte auf ihn.'

    assert h.tempus_in_rede_pruefen(text) == []


def test_tempus_rede_plural_praesens_ist_kein_treffer():
    assert h.tempus_in_rede_pruefen('„Wir warten, sie arbeiten und wir fürchten nichts.“') == []


# --- Unbekannte Namen --------------------------------------------------------

def test_unbekannte_namen_meldet_namenswechsel():
    text = (
        'Herzog Heinrich trat in den Raum. „Martha“, sagte der Herzog, „dies ist Nina.“ '
        'Er wandte sich an Agnes. Agnes konnte kaum glauben, was sie hörte. '
        'Dann nickte Agnes und lächelte.'
    )

    findings = h.unbekannte_namen_pruefen(text, GERUEST, STAND)

    assert [f.code for f in findings] == ["unbekannter_name"]
    assert "Heinrich" in findings[0].meldung
    assert "Agnes" in findings[0].meldung
    assert "Nina" not in findings[0].meldung
    assert "Martha" not in findings[0].meldung
    assert "Daniel" not in findings[0].meldung


def test_unbekannte_namen_ignoriert_bekannte_namen_und_satzanfaenge():
    text = (
        'Nina nickte. Dann sagte Martha leise etwas. Plötzlich lächelte Nina. '
        'Vielleicht gab es Hoffnung. Vielleicht fand sie Arbeit. „Danke, Herzog Daniel.“'
    )

    assert h.unbekannte_namen_pruefen(text, GERUEST, STAND) == []


def test_unbekannte_namen_absatzgrenze_macht_kein_wort_zum_namen():
    text = "Martha bat\n\nNachdem sie fertig war, nickte Nina."

    assert h.unbekannte_namen_pruefen(text, GERUEST, STAND) == []


def test_unbekannte_namen_ohne_referenz_keine_pruefung():
    assert h.unbekannte_namen_pruefen("Herzog Heinrich lächelte.", "", "") == []


def test_alle_nachbearbeitungs_checks_enthaelt_neue_pruefungen():
    text = 'Herzog Heinrich nickte. „Ich hoffte es.“'

    codes = {f.code for f in h.alle_nachbearbeitungs_checks(text, GERUEST, "mild", stand=STAND)}

    assert {"tempus_rede", "unbekannter_name"} <= codes


# --- Autor-Systemprompt --------------------------------------------------------

def test_autor_system_prompt_enthaelt_allgemeine_regeln(tmp_path):
    (tmp_path / "personas").mkdir()
    (tmp_path / "personas" / "autor.txt").write_text("EPOCHEN-PERSONA", encoding="utf-8")
    (tmp_path / "projekt").mkdir()

    prompt = pipeline._autor_system_prompt(tmp_path)

    assert prompt.startswith("EPOCHEN-PERSONA")
    assert "gesprochene Zeitformen" in prompt
    assert "Namen und Nebenfiguren" in prompt
