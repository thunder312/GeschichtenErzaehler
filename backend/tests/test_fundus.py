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


def test_figur_block_erzeugen_listet_immer_alle_felder():
    block = fu.figur_block_erzeugen(
        fu.FigurEintrag(name="Ullrich", alter="20 Jahre", stand="Grafensohn/Ritter",
                         eigenschaften="denkt sehr fortschrittlich-liberal für seine Zeit",
                         aussehen="160cm groß, muskulös, fein geschnittenes Gesicht",
                         ziel="Liberalität leben und Hermine sanft auf ihre Pflichten vorbereiten.",
                         angst="Hermine durch seine Vorsicht zu verletzen.",
                         geheimnis="Seine liberale Art hält er vor seinen Eltern geheim."),
        "Die Spuren der Neuzeit",
    )
    assert block == (
        "### Ullrich\n"
        "- Alter: 20 Jahre\n"
        "- Stand/Rolle: Grafensohn/Ritter\n"
        "- Eigenschaften: denkt sehr fortschrittlich-liberal für seine Zeit\n"
        "- Aussehen: 160cm groß, muskulös, fein geschnittenes Gesicht\n"
        "- Ziel: Liberalität leben und Hermine sanft auf ihre Pflichten vorbereiten.\n"
        "- Angst: Hermine durch seine Vorsicht zu verletzen.\n"
        "- Geheimnis: Seine liberale Art hält er vor seinen Eltern geheim.\n"
        "- Geschichten: Die Spuren der Neuzeit\n"
    )


def test_figur_block_erzeugen_laesst_unbekannte_felder_leer_statt_wegzulassen():
    block = fu.figur_block_erzeugen(fu.FigurEintrag(name="Nina"), "Testgeschichte")
    assert "- Alter: \n" in block
    assert "- Stand/Rolle: \n" in block
    assert "- Eigenschaften: \n" in block
    assert "- Aussehen: \n" in block
    assert "- Ziel: \n" in block
    assert "- Angst: \n" in block
    assert "- Geheimnis: \n" in block
    assert "- Geschichten: Testgeschichte\n" in block


def test_ist_plausibler_figurenname_verwirft_feld_bezeichner():
    for wort in ("Ziel", "geheimnis", "Größte Angst", "Entwicklungsbogen", "  Eigenschaften  ", "Aussehen"):
        assert fu.ist_plausibler_figurenname(wort) is False


def test_ist_plausibler_figurenname_akzeptiert_echte_namen():
    for name in ("Agnes", "Lady Amelia Hartwell", "Pastor Jennrich"):
        assert fu.ist_plausibler_figurenname(name) is True


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
