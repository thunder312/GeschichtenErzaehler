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
_KAPITEL_MUSTER = rf"Kapitel\s+(\d{{1,2}}|{_ZAHLWOERTER_MUSTER})\b"


def kapitelplan_erkennen(geruest: str) -> dict[int, int]:
    """Liest Kapitelnummern und Zielwortzahlen direkt aus dem Kapitelplan.
    Ergebnis z.B. {1: 1500, 2: 1600, 6: 1300} - auch bei Luecken bleiben
    erkannte Eintraege gueltig, fehlende liefern schlicht keinen Zielwert."""
    ergebnis: dict[int, int] = {}
    treffer = list(re.finditer(_KAPITEL_MUSTER, geruest, re.IGNORECASE))
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
    treffer = list(re.finditer(_KAPITEL_MUSTER, geruest, re.IGNORECASE))
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


def jahr_erkennen(geruest: str) -> str:
    """Fallback-Kette: 'Jahr: 1815' -> irgendeine 4-stellige 12../19../20..-
    Zahl -> 'unbekannt'."""
    treffer = re.search(r"Jahr\s*[:\-]?\s*(\d{1,5})", geruest, re.IGNORECASE)
    if not treffer:
        treffer = re.search(r"\b([12][0-9]{3})\b", geruest)
    return treffer.group(1) if treffer else "unbekannt"


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
        treffer = re.search(r"Jahr\s*[:\-]?\s*(\d{1,5})", block, re.IGNORECASE)
        if treffer:
            return treffer.group(1)
    return jahr_erkennen(geruest)


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
    """Liefert den ROLLEN-Schluessel des Autor-Modells. Fehlt die Angabe,
    gilt automatisch 'autor' (Hermes3) - unveraendertes Verhalten fuer
    Bestandsprojekte. Das Label wird bewusst mit (?:...)+  VOR der Erfassung
    beliebig oft konsumiert, nicht nur einmal - der Architekt hat es bei
    einem Live-Projekt ("Das-Echo-der-Verpflichtung-Ein-Geheimnis-in-
    Winterbottom-Hall") verdoppelt ins Geruest geschrieben
    ("Autor-Modell: Autor-Modell: Mistral"). Ohne das (?:...)+ wuerde die
    einfache Version des Musters dann "Autor-Modell" selbst als Wert
    einfangen statt "Mistral" und der Autor faelschlich auf Hermes3
    zurueckfallen."""
    treffer = re.search(r"(?:Autor-Modell\s*[:\-]?\s*)+([A-Za-z0-9 ]+)", geruest, re.IGNORECASE)
    if not treffer:
        return "autor"
    wert = treffer.group(1).lower()
    if "mistral" in wert:
        return "autor_mistral"
    if "qwen" in wert:
        return "autor_qwen"
    return "autor"


def automatische_fortsetzung_aktiviert(geruest: str) -> bool:
    """Default AUS, auch wenn das Feld fehlt - bewusst der sicherere
    Standard (siehe Bedienungsanleitung Abschnitt 9b). Siehe
    autor_rolle_erkennen() zur Begruendung des (?:...)+ gegen ein vom
    Architekten verdoppeltes Label."""
    treffer = re.search(r"(?:Automatische Fortsetzung\s*[:\-]?\s*)+([A-Za-zÄÖÜäöüß]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return False
    return treffer.group(1).lower().startswith("ein")


def titel_erkennen(geruest: str) -> str | None:
    treffer = re.search(r"##\s*Titel\s*\n+(.+)", geruest)
    return treffer.group(1).strip() if treffer else None


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


def titelseite_erzeugen(geruest: str, epoche: str | None) -> str:
    """Baut Titel + Untertitel-Zeile fuer die erste Kapiteldatei. epoche
    kommt in der GUI aus den Projekt-Metadaten statt aus einer '.epoche'-
    Markerdatei."""
    titel = titel_erkennen(geruest)
    if not titel:
        return ""

    jahr_treffer = re.search(r"Jahr\s*[:\-]?\s*(\d{1,5})", geruest, re.IGNORECASE)
    if not jahr_treffer:
        jahr_treffer = re.search(r"\b([12][0-9]{3})\b", geruest)
    jahr = jahr_treffer.group(1) if jahr_treffer else None

    if epoche and jahr:
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
    "von der Content-Stufe der Geschichte. Antworte NUR mit dem fertigen "
    "Prompt als eine einzige Zeile kommagetrennter Stichworte, ohne "
    "Erklaerung, ohne Anführungszeichen."
)

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
