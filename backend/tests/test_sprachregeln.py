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
