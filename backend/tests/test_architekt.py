from app.core import architekt as arch


def test_nur_erste_frage_kuerzt_bei_mehreren_nummerierten_fragen():
    antwort = (
        "Schoen, dann fangen wir an!\n\n"
        "1. In welcher Epoche soll die Geschichte spielen?\n\n"
        "2. Wie explizit darf es werden?\n"
    )
    gekuerzt = arch.nur_erste_frage(antwort)
    assert "In welcher Epoche" in gekuerzt
    assert "Wie explizit" not in gekuerzt


def test_nur_erste_frage_laesst_einzelne_frage_unveraendert():
    antwort = "1. In welcher Epoche soll die Geschichte spielen?"
    assert arch.nur_erste_frage(antwort) == antwort


def test_ist_geruest_antwort_erkennt_endsignal():
    assert arch.ist_geruest_antwort("# STORY-GERUEST\n\n## Rahmen\n...")
    assert arch.ist_geruest_antwort("   # story-geruest\nweiter")
    assert not arch.ist_geruest_antwort("1. Erste Frage")


def test_ist_geruest_antwort_kapitelplan_nicht_faelschlich_gekuerzt():
    geruest = (
        "# STORY-GERUEST\n\n## Kapitelplan\n"
        "1. Kapitel eins: Start. Zielwortzahl: 1500 Woerter.\n"
        "2. Kapitel zwei: Mitte. Zielwortzahl: 1600 Woerter.\n"
    )
    assert arch.ist_geruest_antwort(geruest)
    # nur_erste_frage wird auf ein Geruest gar nicht erst angewendet (siehe
    # ws_architekt), aber falls doch, darf hier zur Doku klar sein, dass es
    # den Kapitelplan zerschneiden wuerde - deshalb der Aufrufer-seitige Skip.


def test_verlauf_zu_text_verbindet_mit_leerzeile():
    assert arch.verlauf_zu_text(["Ich: Hallo", "Du: Frage 1"]) == "Ich: Hallo\n\nDu: Frage 1"


_BEISPIEL_VERLAUF = [
    "Ich: Lass uns anfangen. Stelle mir die ersten Fragen.",  # verlauf[0]
    "Du: Frage 1 von 15: ...",                                # verlauf[1] = nachrichten[0]
    "Ich: Kurz, 2 Kapitel",                                   # verlauf[2] = nachrichten[1]
    "Du: Frage 2 von 15: ...",                                # verlauf[3] = nachrichten[2]
    "Ich: Voll explizit",                                     # verlauf[4] = nachrichten[3]
    "Du: Frage 3 von 15: ...",                                # verlauf[5], noch offene Frage
]
# nachrichten = verlauf[1:-1] (siehe ArchitektInterviewPage.tsx), also
# nachrichten[i] == verlauf[i + 1]. In diesem Beispiel sind das die eigenen
# Antworten an nachrichten-Index 1 ("Kurz, 2 Kapitel") und 3 ("Voll explizit").


def test_verlauf_gekuerzt_ab_schneidet_alles_ab_der_bearbeiteten_antwort_weg():
    gekuerzt = arch.verlauf_gekuerzt_ab(_BEISPIEL_VERLAUF, 3)
    assert gekuerzt == _BEISPIEL_VERLAUF[:4]


def test_verlauf_gekuerzt_ab_bearbeitet_frueheste_eigene_antwort():
    gekuerzt = arch.verlauf_gekuerzt_ab(_BEISPIEL_VERLAUF, 1)
    assert gekuerzt == _BEISPIEL_VERLAUF[:2]


def test_verlauf_gekuerzt_ab_liefert_none_bei_zu_grossem_index():
    assert arch.verlauf_gekuerzt_ab(_BEISPIEL_VERLAUF, 99) is None


def test_verlauf_gekuerzt_ab_liefert_none_bei_negativem_index():
    assert arch.verlauf_gekuerzt_ab(_BEISPIEL_VERLAUF, -1) is None


def test_verlauf_gekuerzt_ab_liefert_none_wenn_index_auf_architekt_frage_zeigt():
    # nachrichten-Index 0 und 2 zeigen auf "Du: ..."-Fragen, keine eigenen
    # Antworten - duerfen nicht bearbeitbar sein.
    assert arch.verlauf_gekuerzt_ab(_BEISPIEL_VERLAUF, 0) is None
    assert arch.verlauf_gekuerzt_ab(_BEISPIEL_VERLAUF, 2) is None


def test_verlauf_gekuerzt_ab_veraendert_originalliste_nicht():
    original = list(_BEISPIEL_VERLAUF)
    arch.verlauf_gekuerzt_ab(_BEISPIEL_VERLAUF, 1)
    assert _BEISPIEL_VERLAUF == original


def test_ausgangslage_erkennen_extrahiert_abschnitt():
    geruest = (
        "# STORY-GERUEST\n\n"
        "## Ausgangslage vor Kapitel eins\n"
        "Mira steht am Marktplatz und wartet auf ihren Bruder.\n\n"
        "## Offene Punkte\nKeine.\n"
    )
    ausgangslage = arch.ausgangslage_erkennen(geruest)
    assert ausgangslage == "Mira steht am Marktplatz und wartet auf ihren Bruder."


def test_ausgangslage_erkennen_liefert_none_ohne_abschnitt():
    assert arch.ausgangslage_erkennen("# STORY-GERUEST\n\n## Rahmen\nJahr: 1815") is None


def test_figuren_abschnitt_erkennen_extrahiert_abschnitt():
    geruest = (
        "# STORY-GERUEST\n\n"
        "## Figuren\n"
        "Lady Amelia Hartwell, 24, Baronesse, Ziel: ...\n\n"
        "## Konflikt\nSie will heiraten, ihr Vater verbietet es.\n"
    )
    figuren = arch.figuren_abschnitt_erkennen(geruest)
    assert figuren == "Lady Amelia Hartwell, 24, Baronesse, Ziel: ..."


def test_figuren_abschnitt_erkennen_liefert_none_ohne_abschnitt():
    assert arch.figuren_abschnitt_erkennen("# STORY-GERUEST\n\n## Rahmen\nJahr: 1815") is None


def test_figuren_abschnitt_erkennen_ignoriert_unterueberschrift_in_ausgangslage():
    geruest = (
        "# STORY-GERUEST\n\n"
        "## Figuren\n"
        "Lady Amelia Hartwell, 24, Baronesse.\n\n"
        "## Ausgangslage vor Kapitel eins\n"
        "### Figuren\n"
        "Mira steht am Marktplatz.\n\n"
        "### Zeit\nFruehling 1815.\n\n"
        "## Offene Punkte\nKeine.\n"
    )
    figuren = arch.figuren_abschnitt_erkennen(geruest)
    assert figuren == "Lady Amelia Hartwell, 24, Baronesse."
    assert "Mira" not in figuren


def test_transkript_erzeugen_beschriftet_nutzer_und_architekt():
    verlauf = [
        "Ich: Lass uns anfangen. Stelle mir die ersten Fragen.",
        "Du: 1. In welcher Epoche soll die Geschichte spielen?",
        "Ich: Regency, 1815",
    ]
    transkript = arch.transkript_erzeugen(verlauf)
    assert "# Architekten-Gespräch" in transkript
    assert "**Nutzer:** Lass uns anfangen." in transkript
    assert "**Architekt:** 1. In welcher Epoche" in transkript
    assert "**Nutzer:** Regency, 1815" in transkript
