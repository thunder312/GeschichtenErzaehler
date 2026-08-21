"""Fuehrt die Funde der beiden PARALLEL laufenden Pruefer-Rollen
("anachronismus"/"stimmigkeit" aus der Rolle "anachronismus", "kontinuitaet"
aus der gleichnamigen Rolle) deterministisch zusammen - ohne weiteren
KI-Aufruf, wie vom Nutzer gewuenscht. Zwei Funde, deren Fundstellen im
Kapiteltext ueberlappen, werden zu EINEM Eintrag mit mehreren Kategorie-Tags
zusammengefuehrt; stimmen ihre Vorschlaege nicht ueberein, wird der Eintrag
als Konflikt markiert statt einen der beiden Vorschlaege zu bevorzugen.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

# Bereits einmal ("Die-Schwerkraft-der-Erinnerung.md"-Vorfall) UND ein
# zweites Mal ("Schatten-ueber-Luxor...md") bewaehrter Filter gegen zwei
# verwandte, aber verschiedene Fehlerbilder eines Pruefer-"vorschlag": ein
# liegen gebliebener
# Redaktionskommentar/dupliziertes Textfragment (viel laenger als die
# fundstelle - Laengen-Heuristik) ODER eine woertliche Anweisung ANS SCHREIB-
# BZW. PRUEF-TEAM statt direkt einsetzbarem Ersatztext (Muster-Heuristik,
# siehe _ANWEISUNGS_MUSTER unten) - z.B. "Ersetzen Sie 'Luxor' durch...".
# Der zweite Vorfall zeigte, dass die reine Laengen-Heuristik allein NICHT
# reicht: ist die fundstelle selbst schon ein laengerer Satz, passt eine
# ganze Anweisung locker unter die 3x-Grenze und wird trotzdem woertlich in
# den Kapiteltext gespleisst.
#
# Ein DRITTES Fehlerbild (2026-08-17, "Die-Spuren-der-Neuzeit"-Vorfall,
# automatisch_bestaetigen-Lauf ohne Zwischenstopp, dadurch unbeaufsichtigt
# bis in den Live-Text durchgereicht): statt gar keinen Befund zu melden
# (oder bei "unsicher": true "vorschlag": null zu setzen), meldet das Modell
# gelegentlich einen Befund und setzt "vorschlag" auf sein eigenes kurzes
# Pruefungs-Urteil ("Kein Widerspruch.", "Beibehalten.") statt auf
# einsetzbaren Ersatztext. Weder Laengen- noch Anweisungs-Heuristik greift
# hier: das Urteil ist kurz (unterschreitet die Laengen-Grenze locker) und
# enthaelt keine Anweisung an ein Team, sondern eine reine Feststellung -
# siehe _VERDIKT_MUSTER unten.
#
# Ein VIERTES Fehlerbild (2026-08-19, erneut "Schatten-ueber-Luxor..."):
# statt einer Anweisung ANS TEAM (siehe _ANWEISUNGS_MUSTER oben im Modul)
# formuliert das Modell eine allgemeine REGEL/Vorgabe fuer die Figur bzw.
# den Text ("Die Anrede muss durchgehend formell bleiben (Sie/Euch)."). Kein
# Imperativ, keine Anrede ans Team ("Ersetzen Sie...") - grammatisch liest
# sich das wie eine Aussage UEBER den Text, nicht wie ein Zitat AUS ihm,
# deshalb ein eigenes Muster statt eine Erweiterung von _ANWEISUNGS_MUSTER.
# Zwei Signale, beide fuer sich schon selten in echter Erzaehlprosa:
# (1) ein Modalverb ("muss"/"musste") zusammen mit einem Pauschal-Adverb wie
# "durchgehend"/"stets"/"konsequent"/"grundsaetzlich"/"generell" - typisch
# fuer eine Regel-Formulierung, nicht fuer eine einzelne erzaehlte Handlung;
# (2) eine Klammer mit zwei schraeggestrichenen Alternativen ("(Sie/Euch)",
# "(Sie/Ihr)") - echte Prosa entscheidet sich fuer EINE Anrede, sie listet
# nie beide als Option nebeneinander auf.
_REGEL_MUSTER = re.compile(
    r"\bmuss(?:te|ten)?\s+.{0,40}\b(durchgehend|stets|konsequent|grundsätzlich|generell)\b|"
    r"\([^()]{1,20}/[^()]{1,20}\)",
    re.IGNORECASE,
)
_VORSCHLAG_MAX_ABSOLUT = 80
_VORSCHLAG_MAX_VERHAELTNIS = 3

# Formulierungen, die (fast) nie in echter Erzaehlprosa vorkommen, aber
# typisch fuer eine an den Menschen/das Modell gerichtete Anweisung sind -
# sowohl foermliches ("Ersetzen Sie") als auch informelles Imperativ-Register
# ("Fuege ... ein"), sowie die "muss/sollte ... werden"-Passiv-Auflage-Form.
_ANWEISUNGS_MUSTER = re.compile(
    r"\b("
    r"ersetzen sie|w[äa]hlen sie|erg[äa]nzen sie|f[üu]gen sie|beschreiben sie|"
    r"formulieren sie|streichen sie|[äa]ndern sie|geben sie an|"
    # Trennbares Verb "einfuegen" im Imperativ ("Fuege ... ein") - der
    # Abstand zwischen Verbstamm und abgetrenntem Praefix kann bei
    # laengeren Saetzen weit ueber die anfaengliche 20-Zeichen-Grenze
    # hinausgehen (realer Vorfall: "Fuege Katush entweder in das neue
    # Kapitel ein (z.B. ...)" - ueber 40 Zeichen dazwischen), deshalb
    # grosszuegiges Fenster statt knapper Grenze.
    r"f[üu]ge(?:n)?\s+\S+.{0,150}\bein\b|"
    r"w[äa]hle(?:n)?\s+ein(?:e[nrs]?)?\b|"
    r"\bentferne\s+(?:jegliche|alle|diese[nr]?|die|den|das)\b|"
    r"muss(?:te|ten)?\s+.{0,60}\bkorrigiert werden\b|"
    r"sollte(?:n)?\s+.{0,60}\bwerden\b|"
    r"\bbitte\s+(?:eine?|der|die|das)\b"
    r")",
    re.IGNORECASE,
)

# Kurze Pruefungs-Urteile statt Ersatztext - der Vorschlag BEGINNT mit einer
# dieser Feststellungen (mit optionaler kurzer Begruendung dahinter, z.B.
# "Beibehalten, da es die gemeinsame Geschichte der Figuren etabliert."), ist
# also erkennbar ein Urteil UEBER die Fundstelle statt ein Ersatz FUER sie.
# Bewusst am Stringanfang verankert (nicht \b irgendwo im Text): echte
# Erzaehlprosa eroeffnet einen Satz nicht mit diesen abgehackten
# Feststellungen, waehrend z.B. "beibehalten" als Verb mitten in einem
# echten Satz voellig normal ist ("...wollte die alte Tradition
# beibehalten.") und nicht faelschlich blockiert werden soll.
_VERDIKT_MUSTER = re.compile(
    r"^(kein(?:e|er)?\s+(widerspruch|fehler|verstoß|auff[äa]lligkeit(?:en)?|"
    r"korrektur|beanstandung(?:en)?)|beibehalten|unver[äa]ndert|"
    r"bleibt\s+(?:so|gleich|unver[äa]ndert)|korrekt(?:\s+so)?|passt(?:\s+so|\s+schon)?)"
    r"\b",
    re.IGNORECASE,
)


# FUENFTES Fehlerbild (2026-08-21, "Blut-und-Ahornlaub..."-Story,
# Japanisches-Hochmittelalter): kein liegen gebliebener Kommentar und kein
# Urteil, sondern ein "vorschlag", der zwar selbst lesbare Prosa ist, aber am
# Anfang oder Ende einen Satz enthaelt, der im Original-Kapiteltext
# UNMITTELBAR ausserhalb der eigenen "fundstelle" (davor bzw. danach) bereits
# WORTGLEICH oder nur leicht umformuliert (z.B. mit vertauschtem Subjekt)
# steht. Der Pruefer wollte offenbar genug Kontext liefern, um seinen
# Vorschlag natuerlich klingen zu lassen, hat dabei aber einen Nachbarsatz
# reproduziert, der beim Splicen (text[:start] + vorschlag + text[end:])
# unveraendert stehen bleibt - Ergebnis: derselbe Satz taucht zweimal
# hintereinander im Kapiteltext auf. Drei reale Vorkommen in derselben Story
# (Kapitel 1, Kapitel 4 zweimal), siehe test_befunde_merge.py fuer die
# (gekuerzten) Originalzitate. Weder Laengen- noch Anweisungs- noch Regel-
# noch Verdikt-Heuristik greift hier, weil der Vorschlag selbst weder zu lang
# noch eine Anweisung/ein Urteil ist - deshalb ein eigener, kontextbasierter
# Check statt einer weiteren Textmuster-Heuristik.
_KONTEXT_FENSTER = 180
_KONTEXT_AEHNLICHKEIT_SCHWELLE = 0.6
_KONTEXT_MIN_LAENGE = 25


def _normalisiert_locker(text: str) -> str:
    """Wie _normalisiert(), aber behaelt keine Anfuehrungszeichen - fuer den
    Vergleich von Prosa-Fragmenten, bei denen sich Zitatzeichen an der
    Bruchstelle unterscheiden koennen, ohne dass das inhaltlich relevant
    waere."""
    text = re.sub(r"[„“\"'’`]", "", text.lower())
    return " ".join(text.split()).strip()


def vorschlag_dupliziert_kontext(text: str, start: int, end: int, vorschlag: str) -> bool:
    """True, wenn `vorschlag` an Anfang oder Ende einen Textabschnitt
    enthaelt, der dem Text UNMITTELBAR vor `start` bzw. nach `end` im
    Original bereits (fast) entspricht - siehe Kommentar oben. Bewusst ein
    Fenster- statt Satz-Vergleich: eine Duplizierung kann sich ueber eine
    krumme Anzahl Saetze erstrecken (realer Fall: zwei volle Saetze), ein
    reiner Satzgrenzen-Abgleich wuerde das verfehlen. difflib statt
    Wortueberlapp, weil leichte Umformulierungen (vertauschtes Subjekt: "Er
    kuesste sie" -> "Sie kuesste ihn") trotzdem erkannt werden sollen."""
    vorschlag_norm = _normalisiert_locker(vorschlag)
    if len(vorschlag_norm) < _KONTEXT_MIN_LAENGE:
        return False

    danach = _normalisiert_locker(text[end:end + _KONTEXT_FENSTER])
    ende_vorschlag = vorschlag_norm[-_KONTEXT_FENSTER:]
    anfang_danach = danach[:len(ende_vorschlag)]
    if len(anfang_danach) >= _KONTEXT_MIN_LAENGE:
        if difflib.SequenceMatcher(None, ende_vorschlag, anfang_danach).ratio() >= _KONTEXT_AEHNLICHKEIT_SCHWELLE:
            return True

    davor = _normalisiert_locker(text[max(0, start - _KONTEXT_FENSTER):start])
    anfang_vorschlag = vorschlag_norm[:_KONTEXT_FENSTER]
    ende_davor = davor[-len(anfang_vorschlag):] if davor else ""
    if len(ende_davor) >= _KONTEXT_MIN_LAENGE:
        if difflib.SequenceMatcher(None, anfang_vorschlag, ende_davor).ratio() >= _KONTEXT_AEHNLICHKEIT_SCHWELLE:
            return True

    return False


def vorschlag_verdaechtig(fundstelle: str, vorschlag: str) -> bool:
    """True, wenn `vorschlag` eher nach einem liegen gebliebenen
    Redaktionskommentar, einem duplizierten Textfragment, einer Anweisung
    ans Schreib-/Pruef-Team oder einem reinen Pruefungs-Urteil aussieht als
    nach einer echten, direkt einsetzbaren Korrektur von `fundstelle`.
    Bewusst KEIN Wortueberlapp-Check: kurze Kasus-/Genus-Korrekturen (z.B.
    "kein" -> "keine") aendern gerade die Funktionswoerter und teilen sich
    oft nur ein einziges Inhaltswort mit der fundstelle - ein
    Aehnlichkeits-Check wuerde genau diese legitimen Faelle blockieren."""
    if len(vorschlag) > max(_VORSCHLAG_MAX_ABSOLUT, len(fundstelle) * _VORSCHLAG_MAX_VERHAELTNIS):
        return True
    if _ANWEISUNGS_MUSTER.search(vorschlag):
        return True
    if _REGEL_MUSTER.search(vorschlag):
        return True
    return bool(_VERDIKT_MUSTER.match(vorschlag.strip()))


@dataclass
class RoherBefund:
    kategorie: str  # "anachronismus" | "stimmigkeit" | "kontinuitaet"
    fundstelle: str
    beschreibung: str
    sicherheit: str | None  # nur bei anachronismus/stimmigkeit gesetzt
    vorschlag: str | None
    start: int | None
    end: int | None


_SICHERHEIT_RANG = {"hoch": 2, "mittel": 1, "gering": 0}

# Realer Vorfall (2026-08-21, Kapitel 7 derselben "Blut-und-Ahornlaub..."-
# Story): der Kontinuitaets-Pruefer meldete zu Recht offene Faeden fuer eine
# grosse Spanne (~220 Zeichen), setzte aber "vorschlag": null (korrekt laut
# Persona-Regel - eine fehlende Aufloesung laesst sich nicht per Ersatztext
# beheben). Der Anachronismus-Pruefer markierte fuer denselben Bereich nur
# ein kurzes Teilstueck (~49 Zeichen, "Siegel" -> "Zeichen") MIT vorschlag.
# Da nur ein einziger nicht-leerer vorschlag im Cluster uebrig blieb, hat
# befunde_zusammenfuehren() ihn bisher unhinterfragt fuer die GESAMTE
# (durch das Clustering vergroesserte) Fundstelle uebernommen - er deckte
# davon aber nur ~22% ab. Ergebnis beim Splicen: fast der ganze Absatz wurde
# durch das kurze Fragment ersetzt, der Rest des Satzes blieb als
# Textruine stehen. Deshalb: wenn im Cluster mehrere Funde stecken, aber nur
# einer einen vorschlag beisteuert, MUSS dessen EIGENE (Vor-Merge-)Fundstelle
# einen Mindestanteil der gemeinsamen (Nach-Merge-)Fundstelle abdecken -
# sonst wie bei einem echten Widerspruch als Konflikt behandeln, statt den
# Fragment-Vorschlag stillschweigend auf die ganze Spanne anzuwenden.
_SCOPE_MISMATCH_MINDESTANTEIL = 0.6


def _normalisiert(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _hoechste_sicherheit(werte: list[str | None]) -> str | None:
    vorhandene = [w for w in werte if w]
    if not vorhandene:
        return None
    return max(vorhandene, key=lambda w: _SICHERHEIT_RANG.get(w, -1))


def befunde_zusammenfuehren(kapiteltext: str, roh_befunde: list[RoherBefund]) -> list[dict]:
    gefunden = sorted(
        (b for b in roh_befunde if b.start is not None), key=lambda b: b.start,
    )
    nicht_gefunden = [b for b in roh_befunde if b.start is None]

    cluster: list[list[RoherBefund]] = []
    aktuelles_ende = -1
    for befund in gefunden:
        if cluster and befund.start < aktuelles_ende:
            cluster[-1].append(befund)
            aktuelles_ende = max(aktuelles_ende, befund.end)
        else:
            cluster.append([befund])
            aktuelles_ende = befund.end

    ergebnisse: list[dict] = []
    zaehler = 0

    for gruppe in cluster:
        zaehler += 1
        start = min(b.start for b in gruppe)
        end = max(b.end for b in gruppe)
        kategorien: list[str] = []
        for b in gruppe:
            if b.kategorie not in kategorien:
                kategorien.append(b.kategorie)

        vorschlaege = [(b.kategorie, b.vorschlag, b.start, b.end) for b in gruppe if b.vorschlag]
        distinct = {_normalisiert(v) for _, v, _, _ in vorschlaege}
        konflikt = len(distinct) > 1

        gesamt_laenge = end - start
        if (
            not konflikt and len(vorschlaege) == 1 and len(gruppe) > 1
            and gesamt_laenge > 0
        ):
            _, _, eigener_start, eigener_end = vorschlaege[0]
            eigene_laenge = eigener_end - eigener_start
            if eigene_laenge < gesamt_laenge * _SCOPE_MISMATCH_MINDESTANTEIL:
                konflikt = True

        vorschlag = None if konflikt else (vorschlaege[0][1] if vorschlaege else None)
        konflikt_vorschlaege = (
            [{"quelle": q, "text": v} for q, v, _, _ in vorschlaege] if konflikt else None
        )

        ergebnisse.append({
            "id": f"b{zaehler}",
            "kategorien": kategorien,
            "fundstelle": kapiteltext[start:end],
            "beschreibungen": [{"quelle": b.kategorie, "text": b.beschreibung} for b in gruppe],
            "sicherheit": _hoechste_sicherheit([b.sicherheit for b in gruppe]),
            "vorschlag": vorschlag,
            "konflikt": konflikt,
            "konflikt_vorschlaege": konflikt_vorschlaege,
            "gefunden": True,
            "start": start,
            "end": end,
        })

    for b in nicht_gefunden:
        zaehler += 1
        ergebnisse.append({
            "id": f"b{zaehler}",
            "kategorien": [b.kategorie],
            "fundstelle": b.fundstelle,
            "beschreibungen": [{"quelle": b.kategorie, "text": b.beschreibung}],
            "sicherheit": b.sicherheit,
            "vorschlag": b.vorschlag,
            "konflikt": False,
            "konflikt_vorschlaege": None,
            "gefunden": False,
            "start": None,
            "end": None,
        })

    return ergebnisse
