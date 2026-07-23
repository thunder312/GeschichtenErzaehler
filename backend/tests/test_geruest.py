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


def test_jahr_erkennen_mit_explizitem_feld():
    assert g.jahr_erkennen(BEISPIEL_GERUEST) == "1815"


def test_jahr_erkennen_fallback_auf_vierstellige_zahl():
    assert g.jahr_erkennen("Es geschah im Jahre 1920 in einer kleinen Stadt.") == "1920"


def test_jahr_erkennen_unbekannt_ohne_treffer():
    assert g.jahr_erkennen("Kein Datum hier.") == "unbekannt"


def test_jugendschutz_stufe_erkennen():
    assert g.jugendschutz_stufe_erkennen(BEISPIEL_GERUEST) == "angedeutet"
    assert g.jugendschutz_stufe_erkennen("Jugendschutz-Stufe: Jugendfrei") == "jugendfrei"
    assert g.jugendschutz_stufe_erkennen("keine Angabe") == "voll"


def test_autor_rolle_erkennen():
    assert g.autor_rolle_erkennen(BEISPIEL_GERUEST) == "autor_qwen_test"
    assert g.autor_rolle_erkennen("Autor-Modell: Hermes3") == "autor"
    assert g.autor_rolle_erkennen("keine Angabe") == "autor"


def test_automatische_fortsetzung_default_aus():
    assert g.automatische_fortsetzung_aktiviert(BEISPIEL_GERUEST) is False
    assert g.automatische_fortsetzung_aktiviert("Automatische Fortsetzung: Ein") is True
    assert g.automatische_fortsetzung_aktiviert("keine Angabe") is False


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


def test_letztes_geplantes_kapitel():
    assert g.letztes_geplantes_kapitel(BEISPIEL_GERUEST) == 3
    assert g.letztes_geplantes_kapitel("kein Kapitelplan") is None
