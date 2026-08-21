from app.core.befunde_merge import (
    RoherBefund,
    befunde_zusammenfuehren,
    vorschlag_dupliziert_kontext,
    vorschlag_verdaechtig,
)


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


# Woertlich (bis auf Kuerzung) die "vorschlag"-Werte aus einem echten
# Produktiv-Vorfall (Die-Spuren-der-Neuzeit, automatisch_bestaetigen-Lauf
# vom 2026-08-17): statt gar keinen Befund zu melden, meldete das Modell
# einen Befund und setzte "vorschlag" auf sein eigenes kurzes
# Pruefungs-Urteil statt auf Ersatztext - weder Laengen- noch
# Anweisungs-Heuristik hat das abgefangen, die Urteile wurden woertlich in
# den Kapiteltext gespleisst (u.a. der Satz, der den Diener ins Zimmer
# treten liess). Regressionsschutz gegen genau dieses Muster.
def test_vorschlag_verdaechtig_erkennt_kein_widerspruch_urteil():
    fundstelle = (
        "Plötzlich klopfte es an der Tür. Ein Diener trat ein und verbeugte sich tief."
    )
    assert vorschlag_verdaechtig(fundstelle, "Kein Widerspruch.") is True


def test_vorschlag_verdaechtig_erkennt_beibehalten_urteil():
    fundstelle = "Als die Morgendämmerung näher rückte, löschte Ullrich die Kerzen."
    assert vorschlag_verdaechtig(fundstelle, "Beibehalten.") is True
    assert vorschlag_verdaechtig(
        fundstelle, "Beibehalten, da es die gemeinsame Geschichte der Figuren etabliert.",
    ) is True


def test_vorschlag_verdaechtig_erkennt_weitere_urteils_floskeln():
    fundstelle = "Ein beliebiger Satz aus dem Kapitel."
    for urteil in (
        "Keine Auffälligkeiten.", "Kein Fehler.", "Korrekt so.", "Passt.",
        "Unverändert.", "Bleibt unverändert.",
    ):
        assert vorschlag_verdaechtig(fundstelle, urteil) is True


# Woertlich der "vorschlag"-Wert aus einem echten Produktiv-Vorfall
# (Schatten-ueber-Luxor..., 2026-08-19, zweiter Vorfall in diesem Projekt):
# eine allgemeine Anrede-Regel statt eines konkreten Ersatzsatzes landete im
# Kapiteltext. Weder Anweisungs- noch Urteils-Heuristik griff, da hier keine
# Anrede ans Team und kein kurzes Pruefungs-Urteil vorliegt, sondern eine
# Regel-Aussage UEBER den Text. Regressionsschutz gegen genau dieses Muster.
def test_vorschlag_verdaechtig_erkennt_anrede_regel_aussage():
    fundstelle = "Ihr wart eine gute Schuelerin, Katush"
    vorschlag = "Die Anrede muss durchgehend formell bleiben (Sie/Euch)."
    assert vorschlag_verdaechtig(fundstelle, vorschlag) is True


def test_vorschlag_verdaechtig_erkennt_klammer_mit_alternativen():
    assert vorschlag_verdaechtig("bei der Baustätte", "Bei der Baustätte (Sie/Ihr)") is True


def test_vorschlag_verdaechtig_laesst_beibehalten_als_verb_im_satz_durch():
    """'beibehalten' als normales Verb MITTEN in echter Erzaehlprosa (nicht
    als Urteil am Satzanfang) darf nicht blockiert werden."""
    assert vorschlag_verdaechtig(
        "Sie wollte die alte Sitte fortführen.",
        "Sie wollte die alte Sitte ihrer Mutter beibehalten.",
    ) is False


# FUENFTES Fehlerbild (2026-08-21, "Blut-und-Ahornlaub..."-Story,
# Japanisches-Hochmittelalter): der vorschlag selbst ist lesbare Prosa (keine
# der obigen Heuristiken greift), dupliziert aber einen Nachbarsatz, der im
# Original unmittelbar ausserhalb von [start, end) bereits steht. Alle drei
# folgenden Faelle sind woertlich (bis auf Kuerzung) aus dieser echten Story.
def test_vorschlag_dupliziert_kontext_erkennt_dopplung_am_ende():
    """Kapitel 1: der Kontinuitaets-Pruefer haengt an seinen vorschlag zwei
    Saetze an, die im Original direkt NACH der fundstelle schon stehen."""
    text = (
        "Doch dann hörte er ein leises Rascheln hinter sich. Als er sich "
        "umdrehte, sah er, wie Sae eilig etwas vom Boden aufhob – ein paar "
        "verstreute Reiskörner, die aus dem umgekippten Kübel gefallen waren."
        " Ihre Finger zitterten immer noch, doch ihre Bewegungen waren "
        "präzise und geübt. Plötzlich spürte er eine seltsame Verbindung zu "
        "dieser jungen Magd, deren Name er nicht einmal kannte. Es war, als "
        "ob etwas Unausgesprochenes zwischen ihnen floss."
    )
    start = text.index("Doch dann")
    end = text.index("Ihre Finger zitterten")
    vorschlag = (
        "Doch dann hörte er ein leises Rascheln hinter sich. Sae stand etwas "
        "abseits und hielt einen Stapel versiegelter Briefe in den Händen, "
        "die sie eilig vom Boden aufhob. Ihre Finger zitterten immer noch, "
        "doch ihre Bewegungen waren präzise und geübt. Plötzlich spürte er "
        "eine seltsame Verbindung zu dieser jungen Magd, deren Name er nicht "
        "einmal kannte."
    )
    assert vorschlag_dupliziert_kontext(text, start, end, vorschlag) is True


def test_vorschlag_dupliziert_kontext_erkennt_dopplung_am_anfang():
    """Kapitel 4: der vorschlag stellt zwei Saetze VORAN, die im Original
    direkt VOR der fundstelle schon stehen (dort mit vertauschtem Subjekt:
    'Er küsste sie' statt 'Sie küsste ihn')."""
    text = (
        "Er küsste sie noch einmal, voller Zärtlichkeit und Bedauern. Dann "
        "stand er auf und half ihr, sich wieder anzuziehen. Als sie fertig "
        "waren, gingen sie schweigend zum Herrenhof zurück.\n\n"
        "Doch in ihren Herzen wussten sie, dass dies erst der Anfang war."
    )
    start = text.index("Doch in ihren Herzen")
    end = len(text)
    vorschlag = (
        "Sie küsste ihn noch einmal, voller Zärtlichkeit und Bedauern. Dann "
        "stand er auf und half ihr, sich wieder anzuziehen. Als sie fertig "
        "waren, gingen sie schweigend zum Herrenhof zurück. Doch in ihren "
        "Herzen wussten sie, dass die Konsequenzen ihres Kusses weit über "
        "diesen Moment hinausreichten."
    )
    assert vorschlag_dupliziert_kontext(text, start, end, vorschlag) is True


def test_vorschlag_dupliziert_kontext_laesst_echte_korrektur_durch():
    """Gegenprobe: ein vorschlag, der lediglich den Ortsnamen korrigiert und
    danach zwei NEUE (nicht schon vorhandene) Saetze ergaenzt, darf nicht
    blockiert werden - Kapitel 4, konkreter Ortswechsel-Fix desselben
    Vorfalls, diesmal OHNE Dopplung."""
    text = (
        "Die Abendsonne tauchte den Biwa-See in goldenes Licht, als Yorinaga "
        "durch den Garten schlenderte. Die Luft war erfüllt vom Duft der "
        "blühenden Kirschbäume.\n\nEr betrat den Pavillon, wo seine Mutter "
        "bereits wartete."
    )
    start = text.index("Die Abendsonne")
    end = text.index("Die Luft war erfüllt") + len(
        "Die Luft war erfüllt vom Duft der blühenden Kirschbäume."
    )
    vorschlag = (
        "Die Abendsonne tauchte den Herrenhof in goldenes Licht, als "
        "Yorinaga durch den Garten schlenderte. Die Luft war erfüllt vom "
        "Duft der blühenden Kirschbäume."
    )
    assert vorschlag_dupliziert_kontext(text, start, end, vorschlag) is False


def test_scope_mismatch_bei_ueberlappenden_funden_ergibt_konflikt():
    """Kapitel 7: zwei Pruefer melden ueberlappende Funde fuer denselben
    Bereich - Kontinuitaet mit vorschlag=None fuer eine GROSSE Spanne (korrekt
    laut Persona, eine fehlende Aufloesung laesst sich nicht per Ersatztext
    beheben), Anachronismus mit einem vorschlag fuer nur ein kleines
    Teilstueck davon. Ohne Scope-Check wuerde der kleine Vorschlag auf die
    ganze grosse Spanne angewendet und den Rest verschlucken - deshalb muss
    das als Konflikt (nicht automatisch anwendbar) markiert werden."""
    text = (
        "Die Wachen sind zwar noch nicht gekommen, doch die Unstimmigkeit am "
        "Siegel, die Sae bemerkt hat, lässt uns wissen: Wir sind beobachtet."
    )
    grosse_spanne_start = text.index("Die Wachen")
    grosse_spanne_end = len(text)
    kleine_spanne_start = text.index("die Unstimmigkeit am Siegel")
    kleine_spanne_end = kleine_spanne_start + len("die Unstimmigkeit am Siegel, die Sae bemerkt hat")

    roh = [
        RoherBefund(
            kategorie="kontinuitaet", fundstelle=text[grosse_spanne_start:grosse_spanne_end],
            beschreibung="Offener Faden am Ende der Geschichte nicht aufgelöst",
            sicherheit=None, vorschlag=None,
            start=grosse_spanne_start, end=grosse_spanne_end,
        ),
        RoherBefund(
            kategorie="anachronismus", fundstelle=text[kleine_spanne_start:kleine_spanne_end],
            beschreibung="'Siegel' ist anachronistisch",
            sicherheit="mittel", vorschlag="die Unstimmigkeit am Zeichen, die Sae bemerkt hat",
            start=kleine_spanne_start, end=kleine_spanne_end,
        ),
    ]
    ergebnisse = befunde_zusammenfuehren(text, roh)
    assert len(ergebnisse) == 1
    fund = ergebnisse[0]
    assert fund["konflikt"] is True
    assert fund["vorschlag"] is None
    assert fund["konflikt_vorschlaege"] == [
        {"quelle": "anachronismus", "text": "die Unstimmigkeit am Zeichen, die Sae bemerkt hat"}
    ]


def test_scope_match_bei_aehnlich_grossen_ueberlappenden_funden_bleibt_anwendbar():
    """Gegenprobe: deckt der einzige vorschlag im Cluster fast die gesamte
    gemeinsame Spanne ab, bleibt er weiterhin automatisch anwendbar - nur ein
    deutliches Groessen-Missverhaeltnis soll als Konflikt gelten."""
    text = "Der Butler nannte ihn Mr. Hartwell waehrend des Gespraechs."
    start, ende = text.index("Mr. Hartwell"), text.index("Mr. Hartwell") + len("Mr. Hartwell")
    roh = [
        RoherBefund(
            kategorie="anachronismus", fundstelle="Mr. Hartwell", beschreibung="falsche Anrede fuer den Rang",
            sicherheit="hoch", vorschlag="Lord Hartwell", start=start, end=ende,
        ),
        RoherBefund(
            kategorie="kontinuitaet", fundstelle="Mr. Hartwell", beschreibung="unsicher, kein Ersatztext",
            sicherheit=None, vorschlag=None, start=start, end=ende,
        ),
    ]
    ergebnisse = befunde_zusammenfuehren(text, roh)
    assert len(ergebnisse) == 1
    fund = ergebnisse[0]
    assert fund["konflikt"] is False
    assert fund["vorschlag"] == "Lord Hartwell"
