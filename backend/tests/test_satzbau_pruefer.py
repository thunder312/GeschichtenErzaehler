from pathlib import Path

from app.api.pipeline import (
    _anachronismus_roh_befunde,
    _ist_echte_korrektur,
    _kontinuitaet_roh_befunde,
    _lektor_roh_befunde,
    _ohne_eigene_duplikate,
    _satzbau_roh_befunde,
    _text_in_abschnitte_teilen,
)
from app.core import projekt_dateien as pd
from app.core.rollen import ROLLEN

PERSONAS_ORDNER = Path(__file__).parent.parent / "app" / "data" / "personas"


def test_rolle_satzbau_ist_konfiguriert():
    assert "satzbau" in ROLLEN
    assert ROLLEN["satzbau"]["modell"]


def test_persona_datei_pruefer_satzbau_existiert():
    assert (PERSONAS_ORDNER / "pruefer_satzbau.txt").is_file()


def test_neues_projekt_bekommt_pruefer_satzbau_kopiert(tmp_path):
    ziel = tmp_path / "Mein-Projekt"
    leerer_epoche_ordner = tmp_path / "epoche_leer"
    leerer_epoche_ordner.mkdir()

    pd.projekt_anlegen(ziel, leerer_epoche_ordner, PERSONAS_ORDNER, "Test")

    assert (ziel / "personas" / "pruefer_satzbau.txt").is_file()


def test_satzbau_befund_wird_als_lektorat_kategorisiert():
    kapiteltext = "Er ging, wo ihr Griff zitterte leicht, nach Hause."
    antwort_json = (
        '{"befunde": [{"fundstelle": "wo ihr Griff zitterte leicht", '
        '"problem": "Verb-Letzt-Stellung verletzt", '
        '"vorschlag": "wo ihr Griff leicht zitterte"}]}'
    )

    ergebnis = _satzbau_roh_befunde(kapiteltext, antwort_json)

    assert len(ergebnis) == 1
    befund = ergebnis[0]
    assert befund.kategorie == "lektorat"
    assert befund.vorschlag == "wo ihr Griff leicht zitterte"
    assert befund.start is not None and befund.end is not None


def test_satzbau_ohne_befunde_liefert_leere_liste():
    assert _satzbau_roh_befunde("Ein harmloser Satz.", '{"befunde": []}') == []


def test_satzbau_bei_kaputtem_json_meldet_einen_hinweis():
    ergebnis = _satzbau_roh_befunde("Text", "kein json{{{")
    assert len(ergebnis) == 1
    assert ergebnis[0].kategorie == "lektorat"
    assert "nicht gelesen werden" in ergebnis[0].beschreibung


def test_abschnitte_teilen_bei_kurzem_text_liefert_einen_abschnitt():
    text = "Erster Absatz.\n\nZweiter Absatz."
    assert _text_in_abschnitte_teilen(text, ziel_zeichen=1000) == [text]


def test_abschnitte_teilen_schneidet_an_absatzgrenzen():
    absaetze = ["Absatz A ist hier." * 3, "Absatz B ist hier." * 3, "Absatz C ist hier." * 3]
    text = "\n\n".join(absaetze)

    abschnitte = _text_in_abschnitte_teilen(text, ziel_zeichen=60)

    assert len(abschnitte) == 3
    for absatz, abschnitt in zip(absaetze, abschnitte):
        assert abschnitt == absatz
    # Jeder Originalabsatz muss vollstaendig und unveraendert in genau einem
    # Abschnitt wiederzufinden sein - kein Satz darf mitten drin zerschnitten
    # werden.
    assert "\n\n".join(abschnitte) == text


def test_abschnitte_teilen_gruppiert_kleine_absaetze_zusammen():
    absaetze = ["Kurz eins.", "Kurz zwei.", "Kurz drei."]
    text = "\n\n".join(absaetze)

    abschnitte = _text_in_abschnitte_teilen(text, ziel_zeichen=1000)

    assert abschnitte == [text]


def test_abschnitte_teilen_bei_leerem_text():
    assert _text_in_abschnitte_teilen("", ziel_zeichen=1000) == []
    assert _text_in_abschnitte_teilen("   \n\n  ", ziel_zeichen=1000) == []


def test_satzbau_verwirft_wortgleiche_duplikate_aus_derselben_antwort():
    kapiteltext = "Ein Satz, wo ihr Griff zitterte leicht, geht weiter."
    antwort_json = (
        '{"befunde": ['
        '{"fundstelle": "wo ihr Griff zitterte leicht", "problem": "x", "vorschlag": "wo ihr Griff leicht zitterte"},'
        '{"fundstelle": "wo ihr Griff zitterte leicht", "problem": "x", "vorschlag": "wo ihr Griff leicht zitterte"}'
        ']}'
    )

    ergebnis = _satzbau_roh_befunde(kapiteltext, antwort_json)

    assert len(ergebnis) == 1


def test_ist_echte_korrektur_erkennt_wortgleichen_vorschlag():
    assert _ist_echte_korrektur("Ein Satz.", "Ein Satz.") is False
    # Reine Leerraum-Unterschiede zaehlen auch als "wortgleich".
    assert _ist_echte_korrektur("Ein  Satz.", "Ein Satz.") is False


def test_ist_echte_korrektur_erkennt_echten_unterschied():
    assert _ist_echte_korrektur("Ein Satz.", "Ein anderer Satz.") is True


def test_ist_echte_korrektur_ohne_vorschlag_gilt_als_echt():
    assert _ist_echte_korrektur("Ein Satz.", None) is True


def test_lektor_verwirft_funde_mit_wortgleichem_vorschlag():
    kapiteltext = "Ein Satz, der schon richtig ist. Ein zweiter, der es nicht ist."
    antwort_json = (
        '{"befunde": ['
        '{"fundstelle": "Ein Satz, der schon richtig ist.", "problem": "x", '
        '"vorschlag": "Ein Satz, der schon richtig ist."},'
        '{"fundstelle": "Ein zweiter, der es nicht ist.", "problem": "y", '
        '"vorschlag": "Ein zweiter Satz, der es nicht ist."}'
        ']}'
    )

    ergebnis = _lektor_roh_befunde(kapiteltext, antwort_json)

    assert len(ergebnis) == 1
    assert ergebnis[0].fundstelle == "Ein zweiter, der es nicht ist."


def test_anachronismus_behaelt_fund_ohne_vorschlag():
    kapiteltext = "Ein verdaechtiger Satz."
    antwort_json = (
        '{"befunde": [{"kategorie": "anachronismus", "fundstelle": "Ein verdaechtiger Satz.", '
        '"problem": "klingt modern", "sicherheit": "mittel", "vorschlag": null}]}'
    )

    ergebnis = _anachronismus_roh_befunde(kapiteltext, antwort_json)

    assert len(ergebnis) == 1


def test_anachronismus_nullt_anweisung_statt_fund_zu_verwerfen():
    """Regression zum echten Produktiv-Vorfall Schatten-ueber-Luxor...md:
    eine Anweisung ans Team ('Ersetzen Sie...') darf nicht als 'vorschlag'
    durchgereicht werden (sonst landet sie 1:1 im Kapiteltext, siehe
    automatik.befunde_anwenden) - der Fund selbst (die Problembeschreibung)
    bleibt aber erhalten, nur ohne Uebernehmen-Option."""
    kapiteltext = "Luxor: Ein Fluestern gegen das Gesetz der Goetter"
    antwort_json = (
        '{"befunde": [{"kategorie": "anachronismus", "fundstelle": "Luxor: Ein Fluestern gegen das Gesetz der Goetter", '
        '"problem": "Luxor war im Alten Reich kein Machtzentrum.", "sicherheit": "hoch", '
        '"vorschlag": "Ersetzen Sie \'Luxor\' durch \'Memphis\' oder einen generischen Begriff wie \'dem koeniglichen Palast\'."}]}'
    )

    ergebnis = _anachronismus_roh_befunde(kapiteltext, antwort_json)

    assert len(ergebnis) == 1
    assert ergebnis[0].vorschlag is None
    assert ergebnis[0].beschreibung == "Luxor war im Alten Reich kein Machtzentrum."


def test_kontinuitaet_nullt_muss_korrigiert_werden_anweisung():
    kapiteltext = "Eine Geschichte aus dem Altes-Aegypten in der Zeit des Alten Reiches"
    antwort_json = (
        '{"befunde": [{"zitat": "Eine Geschichte aus dem Altes-Aegypten in der Zeit des Alten Reiches", '
        '"widerspruch": "Stand nennt Mittleres Reich.", "beleg": "Stand: Mittleres Reich.", '
        '"unsicher": false, '
        '"vorschlag": "Die Zeitperiode des Settings muss auf das Mittlere Reich korrigiert werden."}]}'
    )

    ergebnis = _kontinuitaet_roh_befunde(kapiteltext, antwort_json)

    assert len(ergebnis) == 1
    assert ergebnis[0].vorschlag is None


def test_lektor_nullt_verdaechtigen_vorschlag():
    kapiteltext = "bei der Baustaette. Nicht mit Respekt, nicht mit Distanz."
    antwort_json = (
        '{"befunde": [{"fundstelle": "bei der Baustaette. Nicht mit Respekt, nicht mit Distanz.", '
        '"problem": "Kasus-Kongruenz", '
        '"vorschlag": "Bitte eine Figur aus dem Alten Reich waehlen, deren Name und Titel zur Epoche passen."}]}'
    )

    ergebnis = _lektor_roh_befunde(kapiteltext, antwort_json)

    assert len(ergebnis) == 1
    assert ergebnis[0].vorschlag is None


def test_ohne_eigene_duplikate_behaelt_erste_reihenfolge():
    class Eintrag:
        def __init__(self, a, b):
            self.a = a
            self.b = b

    eintraege = [Eintrag("x", 1), Eintrag("y", 2), Eintrag("x", 1), Eintrag("x", 3)]

    ergebnis = _ohne_eigene_duplikate(eintraege, ("a", "b"))

    assert [(e.a, e.b) for e in ergebnis] == [("x", 1), ("y", 2), ("x", 3)]
