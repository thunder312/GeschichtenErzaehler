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


def test_kapitelplan_pruefen_ohne_probleme_liefert_leere_liste():
    assert g.kapitelplan_pruefen(BEISPIEL_GERUEST) == []


def test_kapitelplan_pruefen_meldet_fehlende_zielwortzahl():
    # Regression: a-Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen - beim
    # manuellen Nachbearbeiten des Kapitelplans wurden versehentlich ALLE
    # Zielwortzahl-Zeilen entfernt, wodurch kapitelplan_erkennen() jedes
    # Kapitel stillschweigend verschluckte.
    geruest = BEISPIEL_GERUEST.replace(
        "Kapitel zwei: Ein Geheimnis wird angedeutet. Zielwortzahl: 1.600 Woerter.",
        "Kapitel zwei: Ein Geheimnis wird angedeutet.",
    )
    fehler = g.kapitelplan_pruefen(geruest)
    assert len(fehler) == 1
    assert "Kapitel 2" in fehler[0]
    assert "Zielwortzahl" in fehler[0]


def test_kapitelplan_pruefen_meldet_doppelt_deklarierte_kapitelnummer():
    geruest = BEISPIEL_GERUEST.replace(
        "Kapitel 3: Aufloesung. Zielwortzahl: 1.400 Woerter.",
        "Kapitel 1: Aufloesung. Zielwortzahl: 1.400 Woerter.",
    )
    fehler = g.kapitelplan_pruefen(geruest)
    assert any("Kapitel 1" in f and "mehrfach" in f for f in fehler)


def test_kapitelplan_pruefen_ignoriert_kapitel_erwaehnungen_ausserhalb_kapitelplan():
    # "Kapitel N"-Erwaehnungen im Nebenstrang (Indizien-Legung) haben keine
    # Zielwortzahl und sind trotzdem kein Fehler - sie sind kein eigener
    # Kapitelplan-Eintrag.
    geruest = BEISPIEL_GERUEST + "\n## Nebenstrang\nKapitel 5: Ein Hinweis wird gelegt.\n"
    assert g.kapitelplan_pruefen(geruest) == []


def test_kapitelplan_pruefen_ignoriert_kapitel_rueckverweis_im_eigenen_feld():
    # Regression: ein Kapitel, das in seinem eigenen Ort-/Ereignis-Feld auf
    # FRUEHERE Kapitel verweist (z.B. "Ort: ... - erwaehnt in Kapitel 3",
    # "Ereignis: ... aus Kapitel 4 und 6 ..."), darf NICHT wie eine zweite,
    # echte Kapitel-Deklaration behandelt werden - sonst riss das den Block
    # der ECHTEN Ueberschrift vorzeitig ab (die eigene Zielwortzahl-Zeile
    # kam ja erst danach) und loeste ausserdem voellig irrefuehrende
    # "mehrfach deklariert"-Fehler fuer die referenzierten Kapitel aus
    # (Vorfall Kapitel 7 in a-Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen,
    # 2026-08-21).
    geruest = (
        "## Kapitelplan\n"
        "*   **Kapitel 1: Start**\n"
        "    *   Ort: Irgendwo\n"
        "    *   Zielwortzahl: ca. 1000 Woerter.\n"
        "*   **Kapitel 7: Die Fischerhuette**\n"
        "    *   Ort: Die frisch renovierte Fischerhuette - erwaehnt in Kapitel 1\n"
        "    *   Zielwortzahl: ca. 1000 Woerter.\n"
        "    *   Ereignis: gekauft durch Einnahmen aus Kapitel 4 und 6.\n"
    )
    assert g.kapitelplan_pruefen(geruest) == []


def test_kapitelplan_erkennen_verliert_kapitel_mit_rueckverweis_nicht():
    geruest = (
        "## Kapitelplan\n"
        "*   **Kapitel 1: Start**\n"
        "    *   Zielwortzahl: ca. 1000 Woerter.\n"
        "*   **Kapitel 7: Die Fischerhuette**\n"
        "    *   Ort: erwaehnt in Kapitel 1\n"
        "    *   Zielwortzahl: ca. 1200 Woerter.\n"
    )
    assert g.kapitelplan_erkennen(geruest) == {1: 1000, 7: 1200}
    assert g.letztes_geplantes_kapitel(geruest) == 7


def test_kapitel_block_erkennen_mit_rueckverweis_liefert_vollstaendigen_block():
    geruest = (
        "## Kapitelplan\n"
        "*   **Kapitel 7: Die Fischerhuette**\n"
        "    *   Ort: erwaehnt in Kapitel 1\n"
        "    *   Zielwortzahl: ca. 1000 Woerter.\n"
        "    *   Ereignis: aus Kapitel 4 und 6.\n"
    )
    block = g.kapitel_block_erkennen(geruest, 7)
    assert block is not None
    assert "erwaehnt in Kapitel 1" in block
    assert "aus Kapitel 4 und 6" in block


def test_kapitelplan_pruefen_ohne_kapitelplan_abschnitt_liefert_leere_liste():
    # Bewusst kein Fehler - ein Geruest kann noch in Arbeit sein, bevor der
    # Kapitelplan ueberhaupt geschrieben wurde (siehe Docstring).
    assert g.kapitelplan_pruefen("# STORY-GERUEST\n\n## Titel\nOhne Kapitelplan\n") == []


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


def test_titel_erkennen_liefert_einzeiligen_titel():
    assert g.titel_erkennen(BEISPIEL_GERUEST) == "Der Markt von Rothenfeld"


def test_titel_erkennen_schneidet_unaufgeloeste_mehrfachauswahl_ab():
    # Regression: a-Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen (2026-08-20) -
    # der Architekt antwortete mit der unaufgeloesten Auswahl aus Frage 14
    # ("a) Vorschlag ... b) Eigener Titel") statt EINEM Titel. Die Options-
    # Bezeichnung "a) " landete dadurch unveraendert im Ordnernamen.
    geruest = "## Titel\na) Blut und Ahornlaub: Die Ehre des Verbotenen\nb) Eigener Titel\n"
    assert g.titel_erkennen(geruest) == "Blut und Ahornlaub: Die Ehre des Verbotenen"


def test_titel_erkennen_laesst_normalen_titel_mit_klammer_unangetastet():
    # "^[a-d]\\)" darf nur am Zeilenanfang greifen, nicht bei einem Titel,
    # der zufaellig selbst mit einem Buchstaben+Klammer beginnt/eine
    # Klammer enthaelt.
    assert g.titel_erkennen("## Titel\nDer Fall d) Rothenfeld\n") == "Der Fall d) Rothenfeld"


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
