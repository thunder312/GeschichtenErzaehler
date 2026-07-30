from app.core import fundus as fu


def test_leere_vorlage_enthaelt_kommentarblock():
    vorlage = fu.leere_vorlage()
    assert vorlage.startswith("<!--")
    assert "FUNDUS-VORLAGE" in vorlage


def test_epoche_abschnitt_erkennen_liefert_none_ohne_treffer():
    assert fu.epoche_abschnitt_erkennen(fu.leere_vorlage(), "Regency") is None


def test_epoche_abschnitt_erkennen_findet_abschnitt():
    text = fu.leere_vorlage() + "\n## Regency\n\n### Lady Amelia\n- Alter: 24\n\n## Mittelalter\n\n### Bertram\n"
    abschnitt = fu.epoche_abschnitt_erkennen(text, "Regency")
    assert "Lady Amelia" in abschnitt
    assert "Bertram" not in abschnitt


def test_figuren_zusammenfuehren_legt_neue_epoche_und_figur_an():
    ergebnis = fu.figuren_zusammenfuehren(
        fu.leere_vorlage(), "Regency", "Der Markt von Rothenfeld",
        [fu.FigurEintrag(name="Lady Amelia Hartwell", alter="24", stand="Baronesse", eigenschaften="eigensinnig")],
    )
    assert "## Regency" in ergebnis
    assert "### Lady Amelia Hartwell" in ergebnis
    assert "- Geschichten: Der Markt von Rothenfeld" in ergebnis


def test_figuren_zusammenfuehren_ergaenzt_geschichte_bei_bestehender_figur():
    basis = fu.figuren_zusammenfuehren(
        fu.leere_vorlage(), "Regency", "Der Markt von Rothenfeld",
        [fu.FigurEintrag(name="Lady Amelia Hartwell", alter="24", stand="Baronesse", eigenschaften="eigensinnig")],
    )
    ergebnis = fu.figuren_zusammenfuehren(
        basis, "Regency", "Ein Skandal in Mayfair",
        [fu.FigurEintrag(name="Lady Amelia Hartwell")],
    )
    assert ergebnis.count("### Lady Amelia Hartwell") == 1
    assert "- Geschichten: Der Markt von Rothenfeld, Ein Skandal in Mayfair" in ergebnis
    # von Hand gepflegte Felder bleiben unangetastet
    assert "- Alter: 24" in ergebnis
    assert "- Stand/Rolle: Baronesse" in ergebnis


def test_figuren_zusammenfuehren_ist_case_insensitiv_beim_namensabgleich():
    basis = fu.figuren_zusammenfuehren(
        fu.leere_vorlage(), "Regency", "Erste Testgeschichte",
        [fu.FigurEintrag(name="Lady Amelia Hartwell")],
    )
    ergebnis = fu.figuren_zusammenfuehren(
        basis, "Regency", "Zweite Testgeschichte",
        [fu.FigurEintrag(name="lady amelia hartwell")],
    )
    abschnitt = fu.epoche_abschnitt_erkennen(ergebnis, "Regency")
    assert abschnitt.count("### ") == 1
    assert "Erste Testgeschichte, Zweite Testgeschichte" in abschnitt


def test_figuren_zusammenfuehren_dedupliziert_gleiche_geschichte():
    basis = fu.figuren_zusammenfuehren(
        fu.leere_vorlage(), "Regency", "Testgeschichte Rothenfeld",
        [fu.FigurEintrag(name="Lady Amelia Hartwell")],
    )
    ergebnis = fu.figuren_zusammenfuehren(
        basis, "Regency", "Testgeschichte Rothenfeld",
        [fu.FigurEintrag(name="Lady Amelia Hartwell")],
    )
    abschnitt = fu.epoche_abschnitt_erkennen(ergebnis, "Regency")
    assert abschnitt.count("Testgeschichte Rothenfeld") == 1


def test_figuren_zusammenfuehren_trennt_epochen():
    basis = fu.figuren_zusammenfuehren(
        fu.leere_vorlage(), "Regency", "Geschichte A",
        [fu.FigurEintrag(name="Lady Amelia")],
    )
    ergebnis = fu.figuren_zusammenfuehren(
        basis, "Mittelalter", "Geschichte B",
        [fu.FigurEintrag(name="Bertram")],
    )
    regency = fu.epoche_abschnitt_erkennen(ergebnis, "Regency")
    mittelalter = fu.epoche_abschnitt_erkennen(ergebnis, "Mittelalter")
    assert "Lady Amelia" in regency
    assert "Bertram" not in regency
    assert "Bertram" in mittelalter
    assert "Lady Amelia" not in mittelalter


def test_figuren_zusammenfuehren_mehrere_figuren_gleiche_geschichte():
    ergebnis = fu.figuren_zusammenfuehren(
        fu.leere_vorlage(), "Regency", "Der Markt von Rothenfeld",
        [fu.FigurEintrag(name="Lady Amelia"), fu.FigurEintrag(name="Lord Whitmore")],
    )
    assert "### Lady Amelia" in ergebnis
    assert "### Lord Whitmore" in ergebnis
