from app.core import geruest as g

BEISPIEL_GERUEST = """
# STORY-GERUEST

## Rahmen
Jahr: 1815
Jugendschutz-Stufe: Angedeutet
Autor-Modell: Qwen3
Automatische Fortsetzung: Aus
Erzaehlperspektive: Dritte Person

## Titel
Der Markt von Rothenfeld

## Kapitelplan
Kapitel 1: Ankunft auf dem Markt. Zielwortzahl: 1.500 Woerter.
Kapitel zwei: Ein Geheimnis wird angedeutet. Zielwortzahl: 1.600 Woerter.
Kapitel 3: Aufloesung. Zielwortzahl: 1.400 Woerter.
"""


def test_kapitelplan_erkennen_ziffern_und_zahlwoerter():
    plan = g.kapitelplan_erkennen(BEISPIEL_GERUEST)
    assert plan == {1: 1500, 2: 1600, 3: 1400}


def test_kapitel_block_erkennen_liefert_nur_den_gesuchten_block():
    block = g.kapitel_block_erkennen(BEISPIEL_GERUEST, 2)
    assert block is not None
    assert "Geheimnis" in block
    assert "Ankunft" not in block


def test_kapitelplan_platzhalter_erkennen_findet_undefinierte_figur():
    # Realer Vorfall "Das-Echo-der-Verpflichtung-Ein-Geheimnis-in-
    # Winterbottom-Hall" (2026-08-10): Der Architekt liess eine bei der
    # unerhoerten Begebenheit gewaehlte Figur ("ein unerwarteter Gast") im
    # Kapitelplan als Platzhalter stehen, statt sie unter ## Figuren
    # festzulegen - der Autor improvisierte daraufhin beim Schreiben zwei
    # nie wieder aufgegriffene Nebenfiguren.
    geruest = BEISPIEL_GERUEST.replace(
        "Kapitel 3: Aufloesung. Zielwortzahl: 1.400 Woerter.",
        "Kapitel 3: Aufloesung. Anwesende Figuren: Anna, der unerwartete Gast "
        "(Name/Status zu definieren, z.B. eine entfernte Verwandte). "
        "Zielwortzahl: 1.400 Woerter.",
    )
    treffer = g.kapitelplan_platzhalter_erkennen(geruest)
    assert len(treffer) == 1
    assert "zu definieren" in treffer[0]


def test_kapitelplan_platzhalter_erkennen_ignoriert_legitimes_zb_bei_orten():
    # "z.B." bei Orts-/Ereignisangaben ist im Kapitelplan-Format normal und
    # darf NICHT als Platzhalter gemeldet werden (sonst waere die Funktion
    # bei jedem zweiten Kapitelplan falsch positiv).
    geruest = BEISPIEL_GERUEST.replace(
        "Kapitel 3: Aufloesung. Zielwortzahl: 1.400 Woerter.",
        "Kapitel 3: Ort: Ein abgelegener Teil des Anwesens (z.B. ein "
        "verlassener Fluegel oder der Wald). Zielwortzahl: 1.400 Woerter.",
    )
    assert g.kapitelplan_platzhalter_erkennen(geruest) == []


def test_kapitelplan_platzhalter_erkennen_ignoriert_offene_punkte_ausserhalb_kapitelplan():
    geruest = BEISPIEL_GERUEST + "\n## Offene Punkte\nDie Zukunft der Figuren ist noch offen.\n"
    assert g.kapitelplan_platzhalter_erkennen(geruest) == []


def test_nebenstrang_abschnitt_erkennen_extrahiert_abschnitt():
    geruest = (
        "# STORY-GERUEST\n\n"
        "## Nebenstrang\n"
        "**Geheimnis:** Ein altes Familiengeheimnis.\n"
        "*   **Kapitel 2:** Ein Hinweis wird gefunden.\n\n"
        "## Kapitelplan\nKapitel 1: ...\n"
    )
    nebenstrang = g.nebenstrang_abschnitt_erkennen(geruest)
    assert nebenstrang is not None
    assert "Familiengeheimnis" in nebenstrang
    assert "Kapitelplan" not in nebenstrang


def test_nebenstrang_abschnitt_erkennen_liefert_none_ohne_abschnitt():
    assert g.nebenstrang_abschnitt_erkennen("# STORY-GERUEST\n\n## Rahmen\nJahr: 1815") is None


def test_figuren_abschnitt_erkennen_extrahiert_abschnitt():
    geruest = (
        "# STORY-GERUEST\n\n"
        "## Figuren\n"
        "**Lord Marcus Winterbottom (3. Earl of Devonshire):** 28 Jahre, Earl.\n"
        "**Julia:** 19 Jahre, Magd.\n\n"
        "## Konflikt\nEin Satz.\n"
    )
    figuren = g.figuren_abschnitt_erkennen(geruest)
    assert figuren is not None
    assert "Devonshire" in figuren
    assert "Konflikt" not in figuren


def test_figuren_abschnitt_erkennen_liefert_none_ohne_abschnitt():
    assert g.figuren_abschnitt_erkennen("# STORY-GERUEST\n\n## Rahmen\nJahr: 1815") is None


def test_jahr_erkennen_mit_explizitem_feld():
    assert g.jahr_erkennen(BEISPIEL_GERUEST) == "1815"


def test_jahr_erkennen_fallback_auf_vierstellige_zahl():
    assert g.jahr_erkennen("Es geschah im Jahre 1920 in einer kleinen Stadt.") == "1920"


def test_jahr_erkennen_unbekannt_ohne_treffer():
    assert g.jahr_erkennen("Kein Datum hier.") == "unbekannt"


ZEITSPRUNG_GERUEST = """
# STORY-GERUEST

## Rahmen
Jahr: 1150
Jugendschutz-Stufe: Voll
Autor-Modell: Hermes3
Automatische Fortsetzung: Aus

## Kapitelplan
Kapitel 1: Markttag im Dorf. Epoche: Mittelalter. Jahr: 1150. Zielwortzahl: 1.500 Woerter.
Kapitel zwei: Zeitsprung nach Gegenwart ueber das Amulett. Epoche: Gegenwart. Jahr: 2024. Zielwortzahl: 1.600 Woerter.
Kapitel 3: Rueckkehr ins Mittelalter. Epoche: Mittelalter. Jahr: 1150. Zielwortzahl: 1.400 Woerter.
"""


def test_jahr_fuer_kapitel_erkennen_liest_pro_kapitel_bei_zeitsprung():
    assert g.jahr_fuer_kapitel_erkennen(ZEITSPRUNG_GERUEST, 1) == "1150"
    assert g.jahr_fuer_kapitel_erkennen(ZEITSPRUNG_GERUEST, 2) == "2024"
    assert g.jahr_fuer_kapitel_erkennen(ZEITSPRUNG_GERUEST, 3) == "1150"


def test_jahr_fuer_kapitel_erkennen_faellt_ohne_kapitel_jahr_auf_global_zurueck():
    assert g.jahr_fuer_kapitel_erkennen(BEISPIEL_GERUEST, 2) == "1815"


def test_jugendschutz_stufe_erkennen():
    assert g.jugendschutz_stufe_erkennen(BEISPIEL_GERUEST) == "angedeutet"
    assert g.jugendschutz_stufe_erkennen("Jugendschutz-Stufe: Jugendfrei") == "jugendfrei"
    assert g.jugendschutz_stufe_erkennen("keine Angabe") == "voll"


def test_autor_rolle_erkennen_liefert_immer_autor():
    # Seit 2026-08-13 nur noch EIN Schreiber (Mistral, Rolle "autor") -
    # Hermes3/Qwen3 entfernt. autor_rolle_erkennen() wertet den Geruest-Text
    # nicht mehr aus, egal was dort (auch aus aelteren Projekten) steht.
    assert g.autor_rolle_erkennen(BEISPIEL_GERUEST) == "autor"
    assert g.autor_rolle_erkennen("Autor-Modell: Hermes3") == "autor"
    assert g.autor_rolle_erkennen("Autor-Modell: Qwen3") == "autor"
    assert g.autor_rolle_erkennen("Autor-Modell: Mistral") == "autor"
    assert g.autor_rolle_erkennen("keine Angabe") == "autor"
    assert g.autor_rolle_erkennen("") == "autor"


def test_automatische_fortsetzung_default_aus():
    assert g.automatische_fortsetzung_aktiviert(BEISPIEL_GERUEST) is False
    assert g.automatische_fortsetzung_aktiviert("Automatische Fortsetzung: Ein") is True
    assert g.automatische_fortsetzung_aktiviert("keine Angabe") is False


def test_automatische_fortsetzung_bei_vom_architekten_verdoppeltem_label():
    assert g.automatische_fortsetzung_aktiviert("Automatische Fortsetzung: Automatische Fortsetzung: Ein") is True
    assert g.automatische_fortsetzung_aktiviert("Automatische Fortsetzung: Automatische Fortsetzung: Aus") is False


def test_ordnername_aus_titel_transliteriert_umlaute():
    assert g.ordnername_aus_titel("Der Markt von Rothenfeld") == "Der-Markt-von-Rothenfeld"
    assert g.ordnername_aus_titel("Über Äpfel & Bäume?!") == "Ueber-Aepfel-Baeume"


def test_titelseite_erzeugen_mit_jahr_und_epoche():
    seite = g.titelseite_erzeugen(BEISPIEL_GERUEST, "Regency")
    assert seite.startswith("# Der Markt von Rothenfeld")
    assert "Regency" in seite
    assert "1815" in seite


def test_titelseite_erzeugen_ohne_titel_liefert_leeren_string():
    assert g.titelseite_erzeugen("## Kein Titel-Abschnitt", None) == ""


def test_titelseite_erzeugen_mit_einleitungssatz_vorlage_ersetzt_platzhalter():
    # Regression: der rohe Epoche-Ordnername ("Altes-Aegypten") ergab im
    # generischen Fallback grammatikalisch falschen Text ("aus dem
    # Altes-Aegypten"). Die Vorlage aus projekt/einleitungssatz.txt hat
    # Vorrang und darf den Ordnernamen nicht mehr verwenden.
    seite = g.titelseite_erzeugen(
        BEISPIEL_GERUEST, "Altes-Aegypten",
        "Eine Geschichte aus dem alten Ägypten im Jahre {jahr} vor Christus",
    )
    assert "Eine Geschichte aus dem alten Ägypten im Jahre 1815 vor Christus" in seite
    assert "Altes-Aegypten" not in seite


def test_titelseite_erzeugen_ohne_vorlage_faellt_auf_epoche_zurueck():
    seite = g.titelseite_erzeugen(BEISPIEL_GERUEST, "Regency", None)
    assert "Eine Geschichte aus dem Regency im Jahre 1815" in seite


def test_letztes_geplantes_kapitel():
    assert g.letztes_geplantes_kapitel(BEISPIEL_GERUEST) == 3
    assert g.letztes_geplantes_kapitel("kein Kapitelplan") is None
