from app.core.fundstellen import finde_fundstelle


def test_exakter_treffer():
    text = "Julian betrat die Bibliothek und sah Cordelia am Fenster stehen."
    bereich = finde_fundstelle(text, "sah Cordelia am Fenster")
    assert bereich == (text.index("sah Cordelia am Fenster"), text.index("sah Cordelia am Fenster") + len("sah Cordelia am Fenster"))


def test_toleranter_treffer_bei_anfuehrungszeichen():
    text = 'Er sagte „Ich komme gleich" und ging.'
    bereich = finde_fundstelle(text, 'Er sagte "Ich komme gleich" und ging.')
    assert bereich is not None
    start, ende = bereich
    assert text[start:ende] == text


def test_toleranter_treffer_bei_whitespace():
    text = "Der Satz  hat   unregelmaessigen   Whitespace."
    bereich = finde_fundstelle(text, "Der Satz hat unregelmaessigen Whitespace.")
    assert bereich is not None
    start, ende = bereich
    assert text[start:ende] == text


def test_fuzzy_treffer_bei_leichter_umformulierung():
    text = "Cordelia trug ein schwarzes Taftkleid, das ihr vom Kragen bis zum Boden reichte."
    bereich = finde_fundstelle(text, "Cordelia trug ein schwarzes Kleid, das vom Kragen bis zum Boden ging.")
    assert bereich is not None


def test_kein_treffer_bei_voelliger_abweichung():
    text = "Der Regen prasselte gegen die Fenster der alten Bibliothek."
    assert finde_fundstelle(text, "Die Sonne schien ueber dem Meer und den Schiffen.") is None


def test_leeres_zitat_liefert_none():
    assert finde_fundstelle("Irgendein Text.", "") is None
    assert finde_fundstelle("Irgendein Text.", "   ") is None
