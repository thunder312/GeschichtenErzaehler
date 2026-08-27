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


_BEISPIEL_FUNDUS = (
    "## Regency\n\n"
    "### Lady Amelia Hartwell\n"
    "- Alter: 24\n"
    "- Stand/Rolle: Baronesse\n"
    "- Eigenschaften: eigensinnig\n"
    "- Aussehen: \n"
    "- Ziel: \n"
    "- Angst: \n"
    "- Geheimnis: \n"
    "- Geschichten: Der Markt von Rothenfeld\n"
    "\n"
    "### Lord Whitmore\n"
    "- Alter: 30\n"
    "- Stand/Rolle: Earl\n"
    "- Eigenschaften: \n"
    "- Aussehen: \n"
    "- Ziel: \n"
    "- Angst: \n"
    "- Geheimnis: \n"
    "- Geschichten: Der Markt von Rothenfeld\n"
    "\n"
    "## Mittelalter\n\n"
    "### Bertram\n"
    "- Alter: 40\n"
    "- Stand/Rolle: Ritter\n"
    "- Eigenschaften: \n"
    "- Aussehen: \n"
    "- Ziel: \n"
    "- Angst: \n"
    "- Geheimnis: \n"
    "- Geschichten: Das Tabu\n"
)


def test_fundus_parsen_liefert_alle_figuren_ueber_alle_epochen():
    figuren = fu.fundus_parsen(fu.leere_vorlage() + "\n" + _BEISPIEL_FUNDUS)
    namen = [(f.epoche, f.name) for f in figuren]
    assert namen == [
        ("Regency", "Lady Amelia Hartwell"),
        ("Regency", "Lord Whitmore"),
        ("Mittelalter", "Bertram"),
    ]


def test_fundus_parsen_liest_felder_in_ordnung_und_ignoriert_vorlage_beispiel():
    figuren = fu.fundus_parsen(fu.leere_vorlage() + "\n" + _BEISPIEL_FUNDUS)
    amelia = figuren[0]
    assert list(amelia.felder.keys()) == fu.STANDARD_FELDER + ["Geschichten"]
    assert amelia.felder["Alter"] == "24"
    assert amelia.felder["Stand/Rolle"] == "Baronesse"
    assert amelia.felder["Geschichten"] == "Der Markt von Rothenfeld"
    # Das "### Vollständiger Name"-Beispiel im Kopf-Kommentar darf nicht als
    # echte Figur auftauchen.
    assert all(f.name != "Vollständiger Name" for f in figuren)


def test_fundus_parsen_serialisieren_ist_stabiler_roundtrip():
    figuren = fu.fundus_parsen(_BEISPIEL_FUNDUS)
    neu = fu.fundus_serialisieren(figuren)
    figuren2 = fu.fundus_parsen("## Platzhalter\n\n" + neu)
    # "## Platzhalter\n\n" nur noetig, damit fundus_parsen() (das vor der
    # ERSTEN "## "-Zeile alles verwirft) auch den allerersten Abschnitt von
    # `neu` sieht - fundus_serialisieren() selbst erzeugt ja direkt mit der
    # echten ersten Epoche.
    figuren_direkt = fu.fundus_parsen("\n" + neu)
    assert [(f.epoche, f.name, f.felder) for f in figuren_direkt] == \
        [(f.epoche, f.name, f.felder) for f in figuren]


def test_fundus_serialisieren_kollabiert_mehrzeiligen_wert_statt_ihn_abzuschneiden():
    """Realer Vorfall: ein mehrere Absaetze langer "Aussehen"-Text verlor
    beim naechsten Speichern alles ab dem zweiten Absatz, weil fundus.md
    strikt eine Zeile pro Feld ist und fundus_parsen() eine Fortsetzungszeile
    ohne fuehrendes "- " stillschweigend ueberspringt (siehe
    fundus.py:feldwert_einzeilig)."""
    mehrzeilig = (
        "Erster Absatz mit einer Beschreibung.\n\n"
        "Zweiter Absatz, der bisher beim naechsten Laden verloren ging."
    )
    figuren = [fu.Figur(epoche="Harry-Potter-Universum", name="Daniel Ertl",
                         felder={"Aussehen": mehrzeilig, "Geschichten": "Test"})]
    text = fu.fundus_serialisieren(figuren)
    # Kollabiert zu EINER Zeile - beide Absaetze bleiben inhaltlich erhalten,
    # nur durch ein Leerzeichen statt einen Zeilenumbruch getrennt.
    assert "- Aussehen: Erster Absatz mit einer Beschreibung. Zweiter Absatz, " \
           "der bisher beim naechsten Laden verloren ging.\n" in text

    figuren_geladen = fu.fundus_parsen("\n" + text)
    assert figuren_geladen[0].felder["Aussehen"] == (
        "Erster Absatz mit einer Beschreibung. Zweiter Absatz, der bisher beim "
        "naechsten Laden verloren ging."
    )


def test_figur_block_erzeugen_kollabiert_mehrzeiligen_wert():
    block = fu.figur_block_erzeugen(
        fu.FigurEintrag(name="Nina", aussehen="Zeile eins.\nZeile zwei."), "Testgeschichte",
    )
    assert "- Aussehen: Zeile eins. Zeile zwei.\n" in block


def test_fundus_serialisieren_gruppiert_nach_epoche_in_erstauftrittsreihenfolge():
    figuren = [
        fu.Figur(epoche="Regency", name="A", felder={"Alter": "1", "Geschichten": ""}),
        fu.Figur(epoche="Mittelalter", name="B", felder={"Alter": "2", "Geschichten": ""}),
        fu.Figur(epoche="Regency", name="C", felder={"Alter": "3", "Geschichten": ""}),
    ]
    text = fu.fundus_serialisieren(figuren)
    assert text.index("## Regency") < text.index("## Mittelalter")
    assert text.index("### A") < text.index("### C")
    assert text.index("## Mittelalter") < text.index("### B")


def testfeld_setzen_haengt_neues_feld_vor_geschichten_ein():
    felder = {"Alter": "20", "Geschichten": "Testgeschichte"}
    fu.feld_setzen(felder, "Blutgruppe", "0 negativ")
    assert list(felder.keys()) == ["Alter", "Blutgruppe", "Geschichten"]
    assert felder["Blutgruppe"] == "0 negativ"


def testfeld_setzen_ueberschreibt_bestehendes_feld_an_ort_und_stelle():
    felder = {"Alter": "20", "Blutgruppe": "0 negativ", "Geschichten": "Testgeschichte"}
    fu.feld_setzen(felder, "Blutgruppe", "AB positiv")
    assert list(felder.keys()) == ["Alter", "Blutgruppe", "Geschichten"]
    assert felder["Blutgruppe"] == "AB positiv"


def test_kopf_kommentar_extrahieren_liefert_alles_vor_erster_epoche():
    text = fu.leere_vorlage() + "\n" + _BEISPIEL_FUNDUS
    kopf = fu.kopf_kommentar_extrahieren(text)
    assert kopf.startswith(fu.leere_vorlage())
    assert kopf + "## Regency" in text
    assert "## Regency" not in kopf


def test_kopf_kommentar_extrahieren_faellt_auf_vorlage_zurueck_ohne_epoche():
    assert fu.kopf_kommentar_extrahieren("") == fu.leere_vorlage()
    assert fu.kopf_kommentar_extrahieren("   ") == fu.leere_vorlage()
