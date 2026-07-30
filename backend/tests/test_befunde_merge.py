from app.core.befunde_merge import RoherBefund, befunde_zusammenfuehren


def test_einzelner_fund_bleibt_unveraendert():
    text = "Ein Satz mit einem Anachronismus im Text."
    start, ende = text.index("Anachronismus"), text.index("Anachronismus") + len("Anachronismus")
    roh = [RoherBefund(
        kategorie="anachronismus", fundstelle="Anachronismus", beschreibung="passt nicht in die Epoche",
        sicherheit="hoch", vorschlag="Zeitfehler", start=start, end=ende,
    )]
    ergebnisse = befunde_zusammenfuehren(text, roh)
    assert len(ergebnisse) == 1
    fund = ergebnisse[0]
    assert fund["kategorien"] == ["anachronismus"]
    assert fund["konflikt"] is False
    assert fund["vorschlag"] == "Zeitfehler"
    assert fund["gefunden"] is True


def test_ueberlappende_funde_gleicher_vorschlag_werden_zusammengefuehrt():
    text = "Sie wechselte ploetzlich von Sie zu Du ohne jeden Anlass im Gespraech."
    start, ende = text.index("von Sie zu Du"), text.index("von Sie zu Du") + len("von Sie zu Du")
    roh = [
        RoherBefund(
            kategorie="stimmigkeit", fundstelle="von Sie zu Du", beschreibung="Anrede wechselt unvermittelt",
            sicherheit="mittel", vorschlag="von Sie zu Sie", start=start, end=ende,
        ),
        RoherBefund(
            kategorie="kontinuitaet", fundstelle="von Sie zu Du", beschreibung="Widerspruch zur vorigen Anrede",
            sicherheit=None, vorschlag="von Sie zu Sie", start=start, end=ende,
        ),
    ]
    ergebnisse = befunde_zusammenfuehren(text, roh)
    assert len(ergebnisse) == 1
    fund = ergebnisse[0]
    assert set(fund["kategorien"]) == {"stimmigkeit", "kontinuitaet"}
    assert fund["konflikt"] is False
    assert fund["vorschlag"] == "von Sie zu Sie"
    assert len(fund["beschreibungen"]) == 2


def test_ueberlappende_funde_mit_widerspruechlichem_vorschlag_ergeben_konflikt():
    text = "Der Butler nannte ihn Mr. Hartwell waehrend des Gespraechs."
    start, ende = text.index("Mr. Hartwell"), text.index("Mr. Hartwell") + len("Mr. Hartwell")
    roh = [
        RoherBefund(
            kategorie="anachronismus", fundstelle="Mr. Hartwell", beschreibung="falsche Anrede fuer den Rang",
            sicherheit="hoch", vorschlag="Lord Hartwell", start=start, end=ende,
        ),
        RoherBefund(
            kategorie="kontinuitaet", fundstelle="Mr. Hartwell", beschreibung="Name weicht vom Stand ab",
            sicherheit=None, vorschlag="Major Hartwell", start=start, end=ende,
        ),
    ]
    ergebnisse = befunde_zusammenfuehren(text, roh)
    assert len(ergebnisse) == 1
    fund = ergebnisse[0]
    assert fund["konflikt"] is True
    assert fund["vorschlag"] is None
    assert {v["text"] for v in fund["konflikt_vorschlaege"]} == {"Lord Hartwell", "Major Hartwell"}


def test_nicht_gefundene_funde_clustern_nie():
    text = "Ein kurzer Kapiteltext ohne die zitierten Stellen."
    roh = [
        RoherBefund(
            kategorie="anachronismus", fundstelle="nicht vorhandenes Zitat A", beschreibung="x",
            sicherheit="gering", vorschlag=None, start=None, end=None,
        ),
        RoherBefund(
            kategorie="kontinuitaet", fundstelle="nicht vorhandenes Zitat B", beschreibung="y",
            sicherheit=None, vorschlag=None, start=None, end=None,
        ),
    ]
    ergebnisse = befunde_zusammenfuehren(text, roh)
    assert len(ergebnisse) == 2
    assert all(f["gefunden"] is False for f in ergebnisse)


def test_transitive_ueberlappung_wird_zu_einem_cluster():
    text = "ABCDEFGHIJ"
    roh = [
        RoherBefund(kategorie="anachronismus", fundstelle="ABCD", beschreibung="a", sicherheit="hoch",
                    vorschlag=None, start=0, end=4),
        RoherBefund(kategorie="stimmigkeit", fundstelle="CDEF", beschreibung="b", sicherheit="hoch",
                    vorschlag=None, start=2, end=6),
        RoherBefund(kategorie="kontinuitaet", fundstelle="FGHIJ", beschreibung="c", sicherheit=None,
                    vorschlag=None, start=5, end=10),
    ]
    ergebnisse = befunde_zusammenfuehren(text, roh)
    assert len(ergebnisse) == 1
    fund = ergebnisse[0]
    assert fund["start"] == 0 and fund["end"] == 10
    assert set(fund["kategorien"]) == {"anachronismus", "stimmigkeit", "kontinuitaet"}
