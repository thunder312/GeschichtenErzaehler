from app.core.befunde_merge import RoherBefund, befunde_zusammenfuehren, vorschlag_verdaechtig


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


# Die folgenden vier Faelle sind woertlich (bis auf Kuerzung) die "vorschlag"-
# Werte aus einem echten Produktiv-Vorfall (Schatten-ueber-Luxor...md): der
# alte Pruefer-Prompt lieferte diese Anweisungen ans Schreib-/Pruef-Team statt
# echtem Ersatztext, und da die zugehoerige fundstelle jeweils lang genug war,
# hat sie die reine Laengen-Heuristik nicht abgefangen - sie wurden woertlich
# in den Kapiteltext gespleisst. Regressionsschutz gegen genau dieses Muster.
def test_vorschlag_verdaechtig_erkennt_ersetzen_sie_anweisung():
    fundstelle = "Luxor: Ein Flüstern gegen das Gesetz der Götter"
    vorschlag = (
        "Ersetzen Sie 'Luxor' durch 'Memphis' oder einen generischen Begriff "
        "wie 'dem königlichen Palast' oder 'dem Tempelkomplex'."
    )
    assert vorschlag_verdaechtig(fundstelle, vorschlag) is True


def test_vorschlag_verdaechtig_erkennt_muss_korrigiert_werden():
    fundstelle = "Eine Geschichte aus dem Altes-Aegypten in der Zeit des Alten Reiches"
    vorschlag = "Die Zeitperiode des Settings muss auf das Mittlere Reich (ca. 2000–1700 v. Chr.) korrigiert werden."
    assert vorschlag_verdaechtig(fundstelle, vorschlag) is True


def test_vorschlag_verdaechtig_erkennt_bitte_waehlen_anweisung():
    fundstelle = "bei der Baustätte"
    vorschlag = "Bitte eine Figur aus dem Alten Reich wählen, deren Name und Titel zur Epoche passen."
    assert vorschlag_verdaechtig(fundstelle, vorschlag) is True


def test_vorschlag_verdaechtig_erkennt_informellen_fuege_ein_imperativ():
    fundstelle = "Die Kammer lag still, doch nicht ruhig."
    vorschlag = (
        "Füge einen Übergang ein, der erklärt, wie die Figuren von der Baustelle "
        "in die Kammer gelangen (z.B. 'Nach einem langen Tag...')."
    )
    assert vorschlag_verdaechtig(fundstelle, vorschlag) is True


def test_vorschlag_verdaechtig_erkennt_fuege_ein_bei_grossem_wortabstand():
    """Regression: derselbe Vorfall nochmal, diesmal mit einem Abstand von
    ueber 40 Zeichen zwischen 'Fuege' und dem abgetrennten 'ein' - ein
    frueheres, zu enges 20-Zeichen-Fenster hat das nicht erkannt."""
    fundstelle = "Katush: Auf der Baustelle des Tempels, körperlich müde, aber mit einem Gefühl der ständigen Unterordnung."
    vorschlag = (
        "Füge Katush entweder in das neue Kapitel ein (z.B. als Beobachter, der aus "
        "der Ferne sichtbar ist) oder entferne jegliche Verweise auf ihn aus dem "
        "Stand, wenn er nicht mehr relevant ist."
    )
    assert vorschlag_verdaechtig(fundstelle, vorschlag) is True


def test_vorschlag_verdaechtig_laesst_echte_kurzkorrektur_durch():
    assert vorschlag_verdaechtig("Luxor", "Memphis") is False
    assert vorschlag_verdaechtig(
        "Die Kammer lag still, doch nicht ruhig.",
        "Nach einem langen Tag auf der Baustelle zogen sie sich in die Kammer zurück. "
        "Dort lag es still, doch nicht ruhig.",
    ) is False
