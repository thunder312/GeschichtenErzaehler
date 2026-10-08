from app.core import sprachregeln as sr

NAMEN = {"Daniel", "Larissa", "Harris"}


def test_numerus_verb_nach_namen():
    text = "Am Abend gingen sie. Daniel und Larissa kehrte am Morgen zurück."
    (b,) = sr.numerus_roh_befunde(text, NAMEN)
    assert b.fundstelle == "Daniel und Larissa kehrte"
    assert b.vorschlag == "Daniel und Larissa kehrten"
    assert text[b.start:b.end] == b.fundstelle


def test_numerus_verb_vor_namen_im_nebensatz_satz():
    text = "Nachdem die Nacht vorübergegangen war, kehrte Daniel und Larissa am Morgen zurück."
    (b,) = sr.numerus_roh_befunde(text, NAMEN)
    assert b.fundstelle == "kehrte Daniel und Larissa"
    assert b.vorschlag == "kehrten Daniel und Larissa"
    assert text[b.start:b.end] == b.fundstelle


def test_numerus_korrekter_plural_und_objekte_bleiben_unberuehrt():
    for text in (
        "Daniel und Larissa kehrten zurück.",
        "Er sprach mit Daniel und Larissa lachte.",
        "Harris sah Daniel und Larissa an.",
        "Sie küsste, sah Daniel und Larissa an.",
    ):
        assert sr.numerus_roh_befunde(text, NAMEN) == [], text


def test_altschreibung():
    text = "Er war bewußt still, daß sie es wußte. Die Regeln hatten sie fast zerissen."
    funde = {b.fundstelle: b.vorschlag for b in sr.altschreibung_roh_befunde(text)}
    assert funde == {"bewußt": "bewusst", "daß": "dass", "wußte": "wusste", "zerissen": "zerrissen"}
    assert sr.altschreibung_roh_befunde("Der Fluss floss. Die Maße stimmten.") == []


def test_spezies_numerus_hinweis_ohne_vorschlag():
    text = "„Wir müssen vorsichtig sein. Diese Spezies... sie sind anders.“"
    (b,) = sr.spezies_numerus_roh_befunde(text)
    assert b.fundstelle == "Diese Spezies... sie sind"
    assert b.vorschlag is None
    assert text[b.start:b.end] == b.fundstelle


def test_spezies_numerus_laesst_stimmige_saetze_in_ruhe():
    for text in (
        "Diese Spezies ist anders, sie ist friedlich.",
        "Unsere Spezies sind so unterschiedlich.",
        "Es scheint, als ob die beobachtenden Spezies näher kommen.",
        "Die Spezies im Tal beobachtete sie. Sie sind weg.",
    ):
        assert sr.spezies_numerus_roh_befunde(text) == [], text


def test_als_ob_indikativ_wird_zu_konjunktiv():
    text = "Sie wurde klein, als ob sie in seiner Gegenwart nichts weiter war als ein Schatten."
    (b,) = sr.als_ob_roh_befunde(text)
    assert (b.fundstelle, b.vorschlag) == ("war", "wäre")
    assert text[b.start:b.end] == "war"


def test_als_ob_mehrere_verben_und_wenn():
    funde = {b.fundstelle: b.vorschlag for b in sr.als_ob_roh_befunde(
        "Er nickte, als ob er das wusste. Es klang, als wenn jede Bewegung eine Sprache sprach.")}
    assert funde == {"wusste": "wüsste", "sprach": "spräche"}


def test_als_ob_laesst_korrekte_und_mehrdeutige_saetze_in_ruhe():
    for text in (
        "Er suchte, als ob er nach Gefahren suchte.",             # schwach: Indikativ = Konjunktiv II
        "Er sah aus, als ob er müde wäre.",                       # bereits Konjunktiv
        "Als ob er nicht schon wüsste, dass die Antwort Ja war.",  # Verb im dass-Satz
        "Sie lachte, als ob nichts geschehen wäre, und ging.",     # "ging" erst nach dem Komma
        "Das war ein Tag, an dem sie ging.",                      # kein "als ob"
    ):
        assert sr.als_ob_roh_befunde(text) == [], text
