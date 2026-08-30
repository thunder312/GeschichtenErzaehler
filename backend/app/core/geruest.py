"""Gerüst-Parsing - portiert aus pre-GUI/novelle.py.

Alle Funktionen hier sind reine Funktionen (kein I/O, kein CLI-Seiteneffekt)
und operieren auf dem rohen geruest.md-Text. Die Regex-Muster sind bewusst
wortgleich zum Original uebernommen (siehe doc/Schnittstellen-Uebersicht.md
Abschnitt 2.1 und 5), damit ein Gerüst, das mit der alten CLI erzeugt wurde,
in der GUI identisch interpretiert wird.
"""
import re

# Deutsche Zahlwoerter 1-20, weil der Architekt Kapitelnummern mal als Ziffer
# ("Kapitel 3"), mal ausgeschrieben ("Kapitel drei") formuliert.
_ZAHLWORT = {
    "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fuenf": 5, "fünf": 5,
    "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11,
    "zwoelf": 12, "zwölf": 12, "dreizehn": 13, "vierzehn": 14,
    "fuenfzehn": 15, "fünfzehn": 15, "sechzehn": 16, "siebzehn": 17,
    "achtzehn": 18, "neunzehn": 19, "zwanzig": 20,
}

_ZAHLWOERTER_MUSTER = "|".join(_ZAHLWORT)
# Verankert auf Zeilenanfang (nur optionaler Bullet-/Fett-Praefix davor
# erlaubt: "*   **Kapitel eins: ...**", "**Kapitel 1: ...**" oder schlicht
# "Kapitel 1: ..."), damit eine blosse Erwaehnung MITTEN in einem anderen
# Feld (z.B. "Ort: ... - erwaehnt in Kapitel 3" oder "Ereignis: ... aus
# Kapitel 4 und 6 ...") NICHT wie eine zweite, echte Kapitel-Deklaration
# behandelt wird. Ohne diese Verankerung riss eine solche Rueckreferenz den
# Block der ECHTEN Kapitel-Ueberschrift vorzeitig ab (die eigentliche
# Zielwortzahl-Zeile kam ja erst danach) - das betroffene Kapitel
# verschwand dadurch komplett aus kapitelplan_erkennen()/
# letztes_geplantes_kapitel(), und kapitelplan_pruefen() lehnte den
# Speicherversuch zusaetzlich mit vollkommen irrefuehrenden Fehlern ab
# ("Kapitel 3: mehrfach deklariert" etc.) - Vorfall: Kapitel 7 in
# Blut-und-Ahornlaub-Die-Ehre-des-Verbotenen referenzierte Kapitel 3/4/6,
# 2026-08-21. Wird IMMER zusammen mit re.MULTILINE verwendet, damit "^" an
# jedem Zeilenanfang greift, nicht nur am Textanfang.
_KAPITEL_MUSTER = rf"^[ \t]*[*-]?[ \t]*\**[ \t]*Kapitel\s+(\d{{1,2}}|{_ZAHLWOERTER_MUSTER})\b"


def kapitelplan_erkennen(geruest: str) -> dict[int, int]:
    """Liest Kapitelnummern und Zielwortzahlen direkt aus dem Kapitelplan.
    Ergebnis z.B. {1: 1500, 2: 1600, 6: 1300} - auch bei Luecken bleiben
    erkannte Eintraege gueltig, fehlende liefern schlicht keinen Zielwert."""
    ergebnis: dict[int, int] = {}
    treffer = list(re.finditer(_KAPITEL_MUSTER, geruest, re.IGNORECASE | re.MULTILINE))
    for i, m in enumerate(treffer):
        roh_nummer = m.group(1).lower()
        nummer = int(roh_nummer) if roh_nummer.isdigit() else _ZAHLWORT.get(roh_nummer)
        if nummer is None or nummer in ergebnis:
            continue
        block_ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(geruest)
        block = geruest[m.end():block_ende]
        wort_treffer = re.search(r"([\d][\d.,]*)\s*w(?:oe|ö)rter", block, re.IGNORECASE)
        if wort_treffer:
            zahl_text = re.sub(r"[.,]", "", wort_treffer.group(1))
            try:
                ergebnis[nummer] = int(zahl_text)
            except ValueError:
                pass
    return ergebnis


def kapitel_block_erkennen(geruest: str, gesuchte_nummer: int) -> str | None:
    """Liefert den vollen Textblock des EINEN gesuchten Kapitels aus dem
    echten Kapitelplan (unterscheidet ihn von blossen Kapitel-Erwaehnungen
    anderswo im Geruest, z.B. im Nebenstrang-Abschnitt)."""
    treffer = list(re.finditer(_KAPITEL_MUSTER, geruest, re.IGNORECASE | re.MULTILINE))
    for i, m in enumerate(treffer):
        roh_nummer = m.group(1).lower()
        nummer = int(roh_nummer) if roh_nummer.isdigit() else _ZAHLWORT.get(roh_nummer)
        if nummer != gesuchte_nummer:
            continue
        block_ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(geruest)
        block = geruest[m.start():block_ende]
        if re.search(r"[\d][\d.,]*\s*w(?:oe|ö)rter", block, re.IGNORECASE):
            return block.strip()
    return None


_KAPITELPLAN_ABSCHNITT_MUSTER = re.compile(
    r"##\s*Kapitelplan\s*\n(.*?)(?=\n##\s|\Z)", re.IGNORECASE | re.DOTALL,
)

# Bewusst eng gefasst auf "Name/Status/Figur ... zu definieren"-artige
# Formulierungen statt z.B. jedes "z.B." im Kapitelplan zu melden - ein
# "z.B." bei einer Orts- oder Ereignis-Angabe (z.B. "Ort: ... (z.B. ein
# verlassener Fluegel oder der Wald)") ist im bestehenden Kapitelplan-Format
# normal und kein Fehlersignal, siehe architekt.txt "## Kapitelplan".
_KAPITELPLAN_PLATZHALTER_MUSTER = re.compile(
    r"\b(?:Name|Status|Figur)\b[^\n]{0,40}\bzu\s+definieren\b"
    r"|\bnoch\s+(?:zu\s+)?(?:benennen|festzulegen|unbekannt)\b"
    r"|\bTBD\b",
    re.IGNORECASE,
)


def kapitelplan_platzhalter_erkennen(geruest: str) -> list[str]:
    """Findet unaufgeloeste Figuren-Platzhalter im Kapitelplan, z.B. "der
    unerwartete Gast (Name/Status zu definieren, z.B. eine entfernte
    Verwandte oder ein alter Freund)" - ein Hinweis, dass eine bei der
    "unerhoerten Begebenheit" gewaehlte Figur nie konkret unter ## Figuren
    festgelegt wurde. Die Autor-Rolle bekommt den kompletten Kapitelplan
    inkl. aller Kapitel mitgeschickt (siehe app/api/pipeline.py) und muss
    einen solchen Platzhalter beim Schreiben selbst improvisatorisch
    aufloesen - im Vorfall "Das-Echo-der-Verpflichtung-Ein-Geheimnis-in-
    Winterbottom-Hall" (2026-08-10) fuehrte das zu zwei nie wieder
    aufgegriffenen Nebenfiguren (Lady Harriet, Sir Reginald Blackwood) in
    Kapitel 3. Durchsucht NUR den Kapitelplan-Abschnitt (nicht z.B.
    '## Offene Punkte', wo "noch offen"-artige Formulierungen legitim
    sind). Liefert die betroffenen Zeilen roh zur Anzeige im Frontend -
    blockiert nichts, ist nur ein Hinweis (siehe app/api/architekt.py)."""
    abschnitt = _KAPITELPLAN_ABSCHNITT_MUSTER.search(geruest)
    if not abschnitt:
        return []
    return [
        zeile.strip() for zeile in abschnitt.group(1).splitlines()
        if _KAPITELPLAN_PLATZHALTER_MUSTER.search(zeile)
    ]


def kapitelplan_pruefen(geruest: str) -> list[str]:
    """Prueft NUR den '## Kapitelplan'-Abschnitt (nicht blosse "Kapitel N"-
    Erwaehnungen anderswo im Geruest, z.B. im Nebenstrang) auf zwei stille
    Fehlerbilder, die kapitelplan_erkennen()/kapitel_block_erkennen() sonst
    klaglos verschlucken:
    - eine Kapitel-Ueberschrift ohne erkennbare Zielwortzahl - dieses
      Kapitel taucht dann in letztes_geplantes_kapitel() und damit im
      Automatikmodus gar nicht erst auf, der meldet faelschlich "keine
      Kapitel-Struktur" (Vorfall a-Blut-und-Ahornlaub-Die-Ehre-des-
      Verbotenen, 2026-08-20 - beim manuellen Nachbearbeiten des
      Kapitelplans waren versehentlich ALLE Zielwortzahl-Zeilen entfernt
      worden).
    - dieselbe Kapitelnummer zweimal deklariert (Copy-Paste-Fehler) -
      kapitelplan_erkennen() behaelt dann stillschweigend nur die ERSTE
      Deklaration, die zweite verschwindet spurlos.

    Liefert eine Liste allgemeinverstaendlicher Fehlermeldungen (leer =
    kein Problem gefunden). ANDERS als kapitelplan_platzhalter_erkennen()
    oben blockiert das hier den Speichervorgang (siehe app/api/projects.py:
    geruest_schreiben) - ein unvollstaendiger Kapitelplan wuerde sonst
    unbemerkt gespeichert und erst Tage spaeter beim Automatik-Schreiben
    auffallen. Fehlt der '## Kapitelplan'-Abschnitt komplett, wird das
    bewusst NICHT gemeldet - ein Geruest kann sich noch in Arbeit befinden,
    bevor der Kapitelplan ueberhaupt geschrieben wurde."""
    abschnitt = _KAPITELPLAN_ABSCHNITT_MUSTER.search(geruest)
    if not abschnitt:
        return []
    text = abschnitt.group(1)
    treffer = list(re.finditer(_KAPITEL_MUSTER, text, re.IGNORECASE | re.MULTILINE))
    gesehen: set[int] = set()
    fehler: list[str] = []
    for i, m in enumerate(treffer):
        roh_nummer = m.group(1).lower()
        nummer = int(roh_nummer) if roh_nummer.isdigit() else _ZAHLWORT.get(roh_nummer)
        if nummer is None:
            continue
        block_ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(text)
        block = text[m.end():block_ende]
        if not re.search(r"[\d][\d.,]*\s*w(?:oe|ö)rter", block, re.IGNORECASE):
            fehler.append(
                f'Kapitel {nummer}: keine Zielwortzahl gefunden (z.B. "Zielwortzahl: ca. 1.000 Wörter").',
            )
        if nummer in gesehen:
            fehler.append(f"Kapitel {nummer}: mehrfach im Kapitelplan deklariert.")
        gesehen.add(nummer)
    return fehler


_NEBENSTRANG_ABSCHNITT_MUSTER = re.compile(
    r"##\s*Nebenstrang\s*\n(.*?)(?=\n##\s|\Z)", re.IGNORECASE | re.DOTALL,
)


def nebenstrang_abschnitt_erkennen(geruest: str) -> str | None:
    """Extrahiert '## Nebenstrang' aus dem fertigen Geruest - Grundlage
    dafuer, dem Kontinuitaets-Pruefer (pruefer_kontinuitaet.txt) zusaetzlich
    zum "Stand nach dem vorigen Kapitel" (nur EIN Kapitel Rueckblick) den
    gesamten geplanten Nebenstrang mitzugeben. Ohne das kann ein ueber
    mehrere Kapitel schleichend fallengelassener Faden (z.B. eine im
    Nebenstrang angelegte Figur, die nach ihrem Auftritt nie wieder erwaehnt
    wird) nicht auffallen, weil der Pruefer nur den EINEN Schritt vorher/
    nachher vergleicht (siehe Vorfall "Das-Echo-der-Verpflichtung-Ein-
    Geheimnis-in-Winterbottom-Hall": Lady Harriet/Sir Reginald Blackwood
    verschwanden nach Kapitel 3 spurlos, ohne dass ein Pruefer das je
    meldete). None, wenn der Abschnitt fehlt oder leer ist."""
    treffer = _NEBENSTRANG_ABSCHNITT_MUSTER.search(geruest)
    if not treffer:
        return None
    inhalt = treffer.group(1).strip()
    return inhalt or None


_FIGUREN_ABSCHNITT_MUSTER = re.compile(
    r"##\s*Figuren\s*\n(.*?)(?=\n##\s|\Z)", re.IGNORECASE | re.DOTALL,
)


def figuren_abschnitt_erkennen(geruest: str) -> str | None:
    """Extrahiert '## Figuren' aus dem fertigen Geruest - kanonische Namen
    und Titel der Hauptfiguren als Referenzliste fuer den Kontinuitaets-
    Pruefer (pruefer_kontinuitaet.txt), damit er einen abweichenden Titel
    oder eine abweichende Anrede im neuen Kapitel gegen die im Geruest
    festgelegte Version pruefen kann, statt sich nur auf das zu verlassen,
    was der Chronist zufaellig im Stand wiederholt hat. None, wenn der
    Abschnitt fehlt oder leer ist."""
    treffer = _FIGUREN_ABSCHNITT_MUSTER.search(geruest)
    if not treffer:
        return None
    inhalt = treffer.group(1).strip()
    return inhalt or None


def jahr_erkennen(geruest: str) -> str:
    """Fallback-Kette: explizite 'Jahr: 1815'-Angabe (laut Architekt-Vorgabe
    MUSS die Zeitangabe im Geruest mit dem Wort "Jahr" davor stehen) -> erste
    vierstellige Zahl im Wert der "Zeitangabe:"-Zeile im Rahmen (z.B.
    "Zeitangabe: 1960er Jahre" oder "Zeitangabe: 1864 bis 1886", falls sich
    die KI nicht exakt an die Vorgabe gehalten hat) -> 'unbekannt'.

    Bewusst KEIN dokumentweiter Fallback-Scan mehr nach irgendeiner
    vierstelligen Zahl (frueherer Stand): der griff leicht daneben, sobald
    die Zeitangabe nicht dem "Jahr davor"-Format entsprach, und fand dann
    z.B. eine Zielwortzahl aus dem Kapitelplan ("1250 Woerter") statt eines
    echten Jahres - mit spuerbaren Folgen, da dieser Wert auch in den
    Anachronismus-Pruefer-Prompt einfliesst (siehe app/api/pipeline.py:
    _pruefe_kapitel)."""
    # "Jahre?" statt nur "Jahr", damit auch die natuerliche Formulierung
    # "im Jahre 1920" (nicht nur "Jahr: 1920") direkt erkannt wird.
    treffer = re.search(r"Jahre?\s*[:\-]?\s*(\d{1,5})", geruest, re.IGNORECASE)
    if treffer:
        return treffer.group(1)
    zeitangabe_zeile = re.search(r"Zeitangabe\s*:?\s*(.+)", geruest, re.IGNORECASE)
    if zeitangabe_zeile:
        zahl = re.search(r"(\d{4})", zeitangabe_zeile.group(1))
        if zahl:
            return zahl.group(1)
    return "unbekannt"


def jahr_fuer_kapitel_erkennen(geruest: str, n: int) -> str:
    """Wie jahr_erkennen(), sucht das 'Jahr: ...' aber zuerst NUR im
    Kapitelplan-Block von Kapitel n, bevor auf das globale Jahr
    zurueckgefallen wird. Noetig fuer Zeitsprung-Projekte (siehe
    app/core/epoche.py:zeitsprung_dateien_zusammenfuehren): dort hat jedes
    Kapitel je nach Epoche ("Epoche: A"/"Epoche: B") eine eigene Zeitangabe -
    ohne diese Funktion wuerde der Anachronismus-Pruefer immer nur das
    globale Jahr des Geruests sehen und z.B. in einem Gegenwarts-Kapitel
    faelschlich nach historischen Anachronismen suchen."""
    block = kapitel_block_erkennen(geruest, n)
    if block:
        treffer = re.search(r"Jahre?\s*[:\-]?\s*(\d{1,5})", block, re.IGNORECASE)
        if treffer:
            return treffer.group(1)
    return jahr_erkennen(geruest)


def vergangene_zeit_fuer_kapitel_erkennen(geruest: str, n: int) -> str:
    """Liest das Feld 'Vergangene Zeit' aus dem Kapitelplan-Block von Kapitel n
    (siehe app/core/epoche.py:architekt_vorlage, '## Kapitelplan' - wie viel
    erzaehlte Zeit seit dem Ende des vorigen Kapitels vergehen soll, z.B.
    "drei Tage später, ein neuer Abend"). Leerer String, wenn das Feld fehlt
    oder bewusst leer gelassen wurde (Kapitel eins, oder der Architekt hat
    die Wahl dem Autor ueberlassen - siehe app/core/epoche.py:autor_vorlage:
    "waehlst du selbst den kuerzesten Zeitsprung"). Genutzt in
    app/api/pipeline.py:_pruefe_kapitel, damit der Kontinuitaets-Pruefer die
    geplante Zeitspanne gegen den tatsaechlich erzaehlten Kapiteltext
    abgleichen kann, statt nur allgemein nach Zeit-Widersprueche zu suchen."""
    block = kapitel_block_erkennen(geruest, n)
    if not block:
        return ""
    treffer = re.search(r"Vergangene Zeit\s*[:\-]?\s*\**\s*(.*)", block, re.IGNORECASE)
    if not treffer:
        return ""
    return treffer.group(1).strip().rstrip("*").strip()


def jugendschutz_stufe_erkennen(geruest: str) -> str:
    """Unbekannt oder nicht gefunden -> 'voll' (sicherer Standard fuer
    Bestandsprojekte ohne diese Frage)."""
    treffer = re.search(r"Jugendschutz-Stufe\s*[:\-]?\s*([A-Za-zÄÖÜäöüß/ ]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return "voll"
    wert = treffer.group(1).lower()
    if "jugendfrei" in wert:
        return "jugendfrei"
    if "angedeutet" in wert or "romantisch" in wert:
        return "angedeutet"
    return "voll"


def autor_rolle_erkennen(geruest: str) -> str:
    """Liefert den ROLLEN-Schluessel des Schreibers. Es gibt seit 2026-08-13
    nur noch EINEN Schreiber (Mistral, Rolle "autor" in app/core/rollen.py -
    Hermes3/Qwen3 wurden entfernt), deshalb liefert diese Funktion immer
    "autor", unabhaengig vom (evtl. noch aus aelteren Projekten stammenden)
    Freitext-Wert im Gerüst. Signatur bewusst beibehalten (nimmt weiterhin
    den Geruest-Text entgegen, auch wenn er nicht mehr ausgewertet wird),
    damit alle bestehenden Aufrufer (z.B. app/api/pipeline.py,
    app/api/projects.py) unveraendert bleiben koennen."""
    return "autor"


def automatische_fortsetzung_aktiviert(geruest: str) -> bool:
    """Default AUS, auch wenn das Feld fehlt - bewusst der sicherere
    Standard (siehe Bedienungsanleitung Abschnitt 9b). Das Label wird
    bewusst mit (?:...)+ VOR der Erfassung beliebig oft konsumiert, nicht
    nur einmal, falls der Architekt es (wie schon bei anderen Feldern live
    beobachtet) verdoppelt ins Geruest schreibt - ohne das (?:...)+ wuerde
    die einfache Version des Musters dann das Label selbst als Wert
    einfangen statt "Ein"/"Aus"."""
    treffer = re.search(r"(?:Automatische Fortsetzung\s*[:\-]?\s*)+([A-Za-zÄÖÜäöüß]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return False
    return treffer.group(1).lower().startswith("ein")


def titel_erkennen(geruest: str) -> str | None:
    treffer = re.search(r"##\s*Titel\s*\n+(.+)", geruest)
    if not treffer:
        return None
    titel = treffer.group(1).strip()
    # Die Architekt-Persona verlangt laut Vorgabe GENAU einen Titel unter
    # "## Titel" (siehe architekt.txt "## Ausgabe") - antwortet aber
    # gelegentlich trotzdem mit der unaufgeloesten Mehrfachauswahl aus
    # Frage 14 ("a) Vorschlag ... b) Eigener Titel"), z.B. wenn ein bereits
    # vollstaendig ausgefuelltes Offline-Vorlage-Dokument im ersten Zug ohne
    # Rueckfrage durchgereicht wird (siehe arch.erste_eingabe_mit_vorlage).
    # Ohne dieses Abschneiden landete die Options-Bezeichnung "a) "
    # unveraendert im Ordnernamen (Vorfall a-Blut-und-Ahornlaub-Die-Ehre-
    # des-Verbotenen, 2026-08-20 - siehe ordnername_aus_titel() unten).
    return re.sub(r"^[a-d]\)\s*", "", titel) or None


def ordnername_aus_titel(titel: str) -> str:
    """Macht aus einem frei geschriebenen Titel ('Der Markt von Rothenfeld')
    einen dateisystem-tauglichen Ordnernamen ('Der-Markt-von-Rothenfeld')."""
    ersatz = {"ä": "ae", "ö": "oe", "ü": "ue",
              "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
    for a, b in ersatz.items():
        titel = titel.replace(a, b)
    titel = re.sub(r"\s+", "-", titel.strip())
    titel = re.sub(r"[^A-Za-z0-9\-_.]", "", titel)
    titel = re.sub(r"-{2,}", "-", titel).strip("-")
    return titel or "Neues-Projekt"


def ordner_lesbarer_name(titel: str) -> str:
    """Wie ordnername_aus_titel(), behaelt aber Leerzeichen/Umlaute/ß bei -
    fuer app/api/epochen.py:epoche_umbenennen(), wo der Ordner der zentralen
    Epochen-Bibliothek lesbar bleiben soll (anders als bei Projektordnern
    gibt es hier keine URLs/Skripte, die auf die ASCII-Kurzform angewiesen
    waeren). Nur echte Dateisystem-Sonderzeichen werden entfernt - Leer-
    zeichen in Ordnernamen sind unter Windows/NTFS und Linux/ext4 gleichermassen
    unproblematisch, solange Aufrufer (wie hier) Pfade nie als rohen
    Shell-String zusammenbauen (siehe app/core/ssh_manager.py:exec_command,
    das dafuer durchgehend shlex.quote() nutzt)."""
    titel = re.sub(r'[\\/:*?"<>|]', "", titel.strip())
    titel = re.sub(r"\s+", " ", titel).strip(" .")
    return titel or "Neue-Epoche"


def titelseite_erzeugen(geruest: str, epoche: str | None, einleitungssatz_vorlage: str | None = None) -> str:
    """Baut Titel + Untertitel-Zeile fuer die erste Kapiteldatei. epoche
    kommt in der GUI aus den Projekt-Metadaten statt aus einer '.epoche'-
    Markerdatei.

    einleitungssatz_vorlage ist der Inhalt von projekt/einleitungssatz.txt
    (siehe app/core/projekt_dateien.py:einleitungssatz_datei) - eine je
    Epoche frei editierbare Satzvorlage mit dem Platzhalter "{jahr}", noetig
    weil der rohe Epoche-Ordnername (z.B. "Altes-Aegypten") grammatikalisch
    nicht einfach in "Eine Geschichte aus dem {epoche}..." eingesetzt werden
    kann (z.B. "aus dem alten Ägypten" statt "aus dem Altes-Aegypten" - ein
    Kasus-/Deklinationsunterschied zwischen Ordnername und Fliesstext, der
    sich nicht automatisch herleiten laesst). Fehlt die Vorlage (aeltere
    Projekte, oder eine Epoche ohne eigene Datei), greift der alte,
    ordnername-basierte Text als Fallback."""
    titel = titel_erkennen(geruest)
    if not titel:
        return ""

    jahr_treffer = re.search(r"Jahr\s*[:\-]?\s*(\d{1,5})", geruest, re.IGNORECASE)
    if not jahr_treffer:
        jahr_treffer = re.search(r"\b([12][0-9]{3})\b", geruest)
    jahr = jahr_treffer.group(1) if jahr_treffer else None

    if einleitungssatz_vorlage and jahr:
        untertitel = einleitungssatz_vorlage.strip().replace("{jahr}", jahr)
    elif epoche and jahr:
        untertitel = f"Eine Geschichte aus dem {epoche} im Jahre {jahr}"
    elif jahr:
        untertitel = f"Eine Geschichte aus dem Jahre {jahr}"
    else:
        untertitel = ""

    zeilen = [f"# {titel}"]
    if untertitel:
        zeilen.append(f"\n*{untertitel}*")
    return "\n".join(zeilen) + "\n\n\n"


def letztes_geplantes_kapitel(geruest: str) -> int | None:
    plan = kapitelplan_erkennen(geruest)
    return max(plan.keys()) if plan else None


# System-Prompt fuer die "cover_prompt"-Persona (siehe app/core/rollen.py) -
# wandelt ein deutsches geruest.md in einen kurzen, stichwortartigen
# DEUTSCHEN Bildprompt-Entwurf um, den der User im Frontend ohne
# Kunst-Vokabel-Englischkenntnisse verstehen und korrigieren kann (siehe
# COVER_PROMPT_UEBERSETZEN_SYSTEM fuer den Schritt nach Englisch, der erst
# unmittelbar vor der Bildgenerierung laeuft). Fest formuliert statt aus
# einer Persona-Datei geladen, weil er epochenunabhaengig ist (anders als
# die Autor-/Architekt-Personas in personas/, die je Epoche unterschiedlich
# sind, siehe app/core/projekt_dateien.py:EPOCHE_PERSONA_DATEIEN).
COVER_PROMPT_SYSTEM = (
    "Du bist ein Prompt-Ingenieur fuer ein Bildgenerierungsmodell "
    "(Stable Diffusion). Du bekommst das Gerüst einer Geschichte (Titel, "
    "Rahmen/Setting, Epoche/Jahr, Hauptfiguren, Konflikt) auf Deutsch. "
    "Fasse daraus einen kurzen, stichwortartigen Bildprompt AUF DEUTSCH "
    "fuer ein Buchcover zusammen: Szene, Schauplatz, Stimmung/Lichtstimmung, "
    "Bildstil (z.B. 'gemalte Illustration', 'episch', 'filmisches Licht'). "
    "Regeln: KEINE Eigennamen von Figuren (das Modell kann damit nichts "
    "anfangen), KEIN Text/Schriftzug im Bild (das Modell kann keinen "
    "lesbaren Text rendern), keine expliziten/sexuellen Inhalte unabhaengig "
    "von der Content-Stufe der Geschichte. KEINE Verneinungen im Prompt "
    "('keine Waffen', 'ohne Gewalt', 'nicht bedrohlich') - das Bildmodell "
    "ignoriert Verneinungen und stellt oft genau das Gegenteil dar; "
    "beschreibe stattdessen positiv, was zu sehen sein soll (statt 'keine "
    "Waffen' -> 'leere Haende'; statt 'nicht bedrohlich' -> 'ruhige, offene "
    "Haltung'). Antworte NUR mit dem fertigen "
    "Prompt als eine einzige Zeile kommagetrennter Stichworte, ohne "
    "Erklaerung, ohne Anführungszeichen."
)

# Wird sowohl in app/api/pipeline.py:cover_prompt_vorschlagen() (sichtbar im
# editierbaren deutschen Prompt-Textfeld) als auch in cover_generieren()
# (unmittelbar vor der Uebersetzung ins Englische) vorangestellt - ein
# Buchcover soll wie ein echtes Buchcover im Hochformat wirken, nicht wie das
# quadratische Standardbild, das sd-server liefert (siehe
# app/core/bild_generierung.py:STANDARD_WIDTH/HEIGHT, bewusst quadratisch
# belassen wegen dort dokumentierter Subjekt-Verdopplungs-Artefakte bei
# anderen Seitenverhaeltnissen). Nur die KOMPOSITION innerhalb des
# quadratischen Bildes wird dadurch vertikaler/hochformatiger, nicht die
# tatsaechlichen Bildmasse.
# Urspruenglich (Commit a1e6927) war der Praefix bewusst NICHT im editierbaren Feld
# sichtbar, nur unsichtbar bei der Generierung ergaenzt - das fuehrte dazu,
# dass er im vorgeschlagenen Prompt nie auftauchte und wie fehlend wirkte.
# Jetzt steht er sichtbar im Vorschlag; cover_generieren() ergaenzt ihn ueber
# cover_prompt_hochformat_sicherstellen() weiterhin zusaetzlich, falls der
# User ihn aus dem Textfeld entfernt oder einen eigenen Prompt ganz ohne ihn
# eintippt - siehe dort.
COVER_PROMPT_HOCHFORMAT_PRAEFIX = "Hochformat, "


def cover_prompt_hochformat_sicherstellen(prompt: str) -> str:
    """Stellt sicher, dass ein Bildprompt mit COVER_PROMPT_HOCHFORMAT_PRAEFIX
    beginnt, ohne ihn ein zweites Mal voranzustellen, falls er (z.B. aus dem
    Vorschlag von cover_prompt_vorschlagen()) bereits vorhanden ist."""
    if prompt.strip().lower().startswith(COVER_PROMPT_HOCHFORMAT_PRAEFIX.strip().lower()):
        return prompt
    return COVER_PROMPT_HOCHFORMAT_PRAEFIX + prompt

# System-Prompt, der den (ggf. vom User auf Deutsch getippten oder
# korrigierten) Bildprompt unmittelbar vor der sd-server-Anfrage ins
# Englische uebersetzt (Stable-Diffusion-Modelle sind auf englische Prompts
# trainiert, siehe app/core/bild_generierung.py). Bewusst eine reine
# Uebersetzung ohne inhaltliche Freiheit - der User hat die Szene bereits
# festgelegt, das Modell soll nichts hinzuerfinden.
COVER_PROMPT_UEBERSETZEN_SYSTEM = (
    "Du uebersetzt einen stichwortartigen Bildprompt fuer ein "
    "Bildgenerierungsmodell (Stable Diffusion) von Deutsch nach Englisch. "
    "Uebersetze moeglichst woertlich, nutze dabei die im Englischen "
    "uebliche Fachterminologie fuer Bildstil/Beleuchtung (z.B. 'painterly "
    "illustration', 'cinematic lighting', 'epic'). Erfinde KEINE neuen "
    "Details, aendere NICHTS am Inhalt, kuerze nichts. Antworte NUR mit "
    "dem uebersetzten Prompt als eine einzige Zeile kommagetrennter "
    "Stichworte, ohne Erklaerung, ohne Anführungszeichen."
)

# System-Prompt fuer die "befund_synthese"-Persona (siehe app/core/rollen.py) -
# fasst bei einem Konflikt-Fund (mehrere Pruefer-Rollen mit sich
# widersprechenden Vorschlaegen fuer dieselbe Textstelle, siehe
# app/core/befunde_merge.py) deren Anmerkungen UND Einzelvorschlaege zu EINEM
# gemeinsamen Ersatztext zusammen - ausgeloest per Klick auf den
# "Zusammenführen"-Button im Konflikt-Block (siehe
# app/api/pipeline.py:befund_synthese()), NICHT automatisch bei jedem
# Pruef-Lauf, damit der normale Lauf nicht zusaetzlich verlangsamt wird.
BEFUND_SYNTHESE_SYSTEM = (
    "Du bist Redakteur. Mehrere unabhaengige Pruefer-Rollen (Anachronismus, "
    "Kontinuitaet, Stimmigkeit, Lektorat) haben fuer DIESELBE Textstelle "
    "je ein eigenes Problem gemeldet und je einen eigenen, isolierten "
    "Ersatztext vorgeschlagen, der jeweils nur SEIN Problem loest - die "
    "Vorschlaege widersprechen sich deshalb.\n\n"
    "## Eingabe\n"
    "ALTER TEXT: die zu ersetzende Originalstelle.\n"
    "ANMERKUNGEN DER PRÜFER: je Pruefer eine kurze Begruendung, was an ALTER "
    "TEXT problematisch ist.\n"
    "EINZELVORSCHLÄGE DER PRÜFER: je Pruefer ein eigener Ersatztext, der nur "
    "SEIN eigenes Problem loest.\n\n"
    "## Aufgabe\n"
    "Schreibe GENAU EINEN neuen Text, der ALLE genannten Probleme "
    "gleichzeitig behebt - nicht nur eines davon, und nicht einfach einen "
    "der Einzelvorschlaege unveraendert uebernehmen. Bleib so nah wie "
    "moeglich am ALTEN TEXT (Inhalt, Figuren, Ereignis, Erzaehlstimme "
    "unveraendert), aendere nur, was zur Behebung der genannten Probleme "
    "noetig ist. Loesen sich zwei Anmerkungen gegenseitig aus (z.B. "
    "widerspruechliche Ortsangaben), entscheide dich fuer die Variante, die "
    "am wenigsten am Rest des Kapitels aendern wuerde.\n\n"
    "## Ausgabe\n"
    "Antworte AUSSCHLIESSLICH mit dem fertigen deutschen Ersatztext, der 1:1 "
    "anstelle von ALTER TEXT in den Kapiteltext eingesetzt werden kann - "
    "keine Erklaerung, keine Aufzaehlung, keine Anfuehrungszeichen, kein "
    "Kommentar davor oder danach."
)

# System-Prompt fuer die "story_frage"-Persona (siehe app/core/rollen.py) -
# beantwortet Nutzerfragen ZU einer laufenden Geschichte (z.B. "wie hiess
# nochmal die Nebenfigur aus Kapitel 2?"), waehrend das Schreiben laeuft
# (siehe app/api/pipeline.py:story_frage). Bewusst strikt lesend/beantwortend
# statt erzaehlend - anders als die Autor-Persona darf sie unter keinen
# Umstaenden die Geschichte fortsetzen oder ausschmuecken, sonst koennte eine
# beilaeufige Frage versehentlich unkontrollierten Prosa-Text erzeugen, der
# faelschlich als Teil der Geschichte missverstanden werden koennte.
STORY_FRAGE_SYSTEM = (
    "Du beantwortest Fragen zu einer laufenden Geschichte, ausschliesslich "
    "auf Basis des mitgelieferten STORY-GERUESTs und des aktuellen Stands "
    "der Geschichte, die dir als Kontext mitgegeben werden. Du schreibst "
    "KEINE Prosa, setzt die Geschichte NICHT fort und schlaegst auch keine "
    "Handlung fuer kommende Kapitel vor - du beantwortest ausschliesslich "
    "die gestellte Frage, kurz und in normaler Alltagssprache. Geht eine "
    "Information aus dem mitgelieferten Text nicht eindeutig hervor, sagst "
    "du das ehrlich (z.B. 'Das geht aus Gerüst und bisherigem Stand nicht "
    "eindeutig hervor.'), statt zu raten oder etwas zu erfinden. Antworte "
    "auf Deutsch."
)
