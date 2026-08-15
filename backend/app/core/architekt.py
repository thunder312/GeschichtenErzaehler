"""Architekten-Interview - portiert aus pre-GUI/novelle.py (cmd_architekt).

Anders als bei den anderen Rollen ist das ein echtes Mehrschritt-Gespraech:
Bei jedem Zug wird der KOMPLETTE bisherige Verlauf (als eingebetteter Text,
"Ich: ..." / "Du: ...") als eine einzelne User-Nachricht an die Rolle
'architekt' geschickt - keine strukturierte messages-Liste, sondern exakt
das Format, das die Architekt-Persona bereits aus dem CLI kennt und auf das
sie mit ihrer Ein-Frage-pro-Antwort-Regel trainiert/instruiert ist.
"""
from __future__ import annotations

import re
import time

_ERSTE_FRAGE_MUSTER = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)

# Extrahiert die STORY-GERUEST-Struktur (inkl. Abschnitts-Platzhaltertexte
# wie "Jahr (vierstellig), Ort, ...") aus einer Architekt-Persona, OHNE den
# "## Regeln"-Abschnitt danach - Grundlage fuer vorlage_erzeugen(). Alle
# Epoche-Personas folgen demselben "## Ausgabe" -> "# STORY-GERUEST" -> ...
# -> "## Regeln"-Muster (siehe app/data/epochen/*/architekt.txt).
_VORLAGE_MUSTER = re.compile(r"(# STORY-GERUEST.*?)\n##\s*Regeln", re.DOTALL)

_AUSGANGSLAGE_MUSTER = re.compile(
    r"##\s*Ausgangslage\s+vor\s+Kapitel\s+eins\s*\n(.*?)(?=\n##\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_FIGUREN_MUSTER = re.compile(
    r"^##[ \t]*Figuren[ \t]*\n(.*?)(?=\n##[ \t]|\Z)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


def nur_erste_frage(antwort: str) -> str:
    """Die Architekten-Persona soll laut ihrer Anweisung nur eine Frage pro
    Nachricht stellen. Ein 8B-Modell haelt sich daran nicht zuverlaessig und
    packt gelegentlich mehrere nummerierte Fragen in eine Antwort - schneidet
    alles ab der zweiten nummerierten Frage ab, damit garantiert nur eine
    Frage angezeigt wird. Wird NICHT auf das fertige Story-Geruest angewandt
    (das hat selbst nummerierte Listen, z.B. den Kapitelplan, die nicht
    faelschlich abgeschnitten werden duerfen)."""
    treffer = list(_ERSTE_FRAGE_MUSTER.finditer(antwort))
    if len(treffer) < 2:
        return antwort
    grenze = treffer[1].start()
    return antwort[:grenze].rstrip()


def ist_geruest_antwort(antwort: str) -> bool:
    """Das fertige Geruest ist das definierte Endsignal der Architekt-
    Persona: sobald eine Antwort mit '# STORY-GERUEST' beginnt, ist das
    Gespraech inhaltlich abgeschlossen und wird nicht mehr gekuerzt."""
    return bool(re.match(r"\s*#\s*STORY-GERUEST", antwort, re.IGNORECASE))


def verlauf_zu_text(verlauf: list[str]) -> str:
    return "\n\n".join(verlauf)


def _grundgeruest(persona_text: str) -> str:
    """Extrahiert die reine STORY-GERUEST-Struktur (siehe _VORLAGE_MUSTER)
    aus einer Architekt-Persona - gemeinsamer Baustein fuer vorlage_erzeugen()
    und handlungstext_extraktion_system(), damit beide Wege (Vorlage von
    Hand ausfuellen vs. per KI aus einem Handlungstext extrahieren) auf
    exakt demselben Zielformat aufbauen. Faellt das Muster nicht (z.B. bei
    einer nutzerdefinierten Persona ohne dieses Muster), bleibt nur die
    nackte Überschrift übrig."""
    treffer = _VORLAGE_MUSTER.search(persona_text)
    return treffer.group(1).strip() if treffer else "# STORY-GERUEST"


def vorlage_erzeugen(persona_text: str) -> str:
    """Baut aus einer Architekt-Persona ein ausfuellbares Vorlage-Dokument
    zum Offline-Vorbereiten (siehe app/api/architekt.py: architekt_vorlage())
    - nutzt die von _grundgeruest() extrahierte STORY-GERUEST-Struktur samt
    ihrer Platzhaltertexte (z.B. "Jahr (vierstellig), Ort, ..."), die in
    jeder Epoche-Persona ohnehin schon als Ausfuellhilfe formuliert ist,
    statt eine zweite, separat zu pflegende Vorlage anzulegen."""
    return (
        "<!-- Fülle so viel wie möglich aus, Lücken sind ok. Beim Import "
        "dieser Datei fragt der Architekt gezielt nur noch nach dem, was "
        "fehlt oder unklar ist - diese Kommentarzeile kann stehen bleiben. -->\n\n"
        + _grundgeruest(persona_text) + "\n"
    )


def handlungstext_extraktion_system(persona_text: str) -> str:
    """System-Prompt fuer den einmaligen (nicht-dialogischen) Extraktions-
    aufruf in app/api/architekt.py: architekt_extraktion() - Grundlage fuer
    den dritten Weg, ein Story-Gerüst zu erzeugen (neben dem gefuehrten
    Interview und der von Hand ausgefuellten Vorlage): ein fertiger
    Handlungstext (z.B. Skript/Inhaltsangabe einer Sendung) wird automatisch
    in dieselbe STORY-GERUEST-Struktur ueberfuehrt wie vorlage_erzeugen()
    (siehe _grundgeruest) - das Ergebnis landet im Frontend in derselben,
    editierbaren Vorlage-Textarea und durchlaeuft danach unveraendert den
    bestehenden erste_eingabe_mit_vorlage()-Weg: Nutzer prueft/bestaetigt
    den Entwurf, der Architekt fragt anschliessend nur noch gezielt nach
    dem, was aus dem Text nicht eindeutig hervorgeht."""
    return (
        "Du analysierst einen vorgegebenen Handlungstext (z.B. das Skript "
        "oder die Inhaltsangabe einer Sendung, eines Films oder einer "
        "Geschichte) und überführst ihn in folgende STORY-GERUEST-Struktur:\n\n"
        + _grundgeruest(persona_text) + "\n\n"
        "Fülle JEDES Feld so weit aus, wie es sich aus dem Handlungstext "
        "eindeutig ergibt. Erfinde NICHTS hinzu - geht ein Punkt aus dem "
        "Text nicht eindeutig hervor (z.B. Jugendschutz-Stufe, Automatische "
        "Fortsetzung, Zielwortzahl, Kapitelaufteilung, Titel), lass ihn als "
        "Platzhalter in eckigen Klammern stehen, z.B. "
        "'[aus Text nicht ersichtlich]'. Antworte NUR mit dem ausgefüllten "
        "Dokument in GENAU dieser Struktur, ohne Einleitung oder Erklärung "
        "davor oder danach."
    )


def erste_eingabe_mit_vorlage(vorlage_text: str) -> str:
    """Ersetzt ERSTE_EINGABE (app/api/architekt.py), wenn der Nutzer ein
    offline ausgefuelltes Vorlage-Dokument importiert hat (siehe
    vorlage_erzeugen). Der Architekt bekommt den Text als Kontext und wird
    angewiesen, nur noch nach fehlenden/unklaren Punkten zu fragen statt den
    kompletten Fragenkatalog von vorne abzuarbeiten - die eigentliche
    Ein-Frage-pro-Antwort-Regel und das STORY-GERUEST-Endsignal aus der
    Persona bleiben dabei unveraendert in Kraft."""
    return (
        "Ich habe folgendes Vorlage-Dokument für diese Geschichte bereits "
        "offline ausgefüllt:\n\n" + vorlage_text.strip() + "\n\n"
        "Prüfe, was daraus schon eindeutig hervorgeht. Stelle mir wie "
        "gewohnt GENAU EINE Frage nach der anderen im Multiple-Choice-"
        "Format, aber NUR zu Punkten, die fehlen, unklar oder "
        "widersprüchlich sind - wiederhole KEINE Frage, deren Antwort "
        "schon eindeutig im Dokument steht. Sobald alles geklärt ist, "
        "fasse direkt das vollständige STORY-GERUEST zusammen, wie gewohnt."
    )


def verlauf_gekuerzt_ab(verlauf: list[str], bearbeite_ab: int) -> list[str] | None:
    """"Schritte zurueckgehen" bzw. eine fruehere Antwort bearbeiten: kuerzt
    den Verlauf auf den Stand VOR der
    eigenen Antwort an Frontend-Index `bearbeite_ab` (siehe ArchitektInterviewPage.tsx:
    Index in `nachrichten`, das den synthetischen ersten Verlauf-Eintrag und
    die noch offene letzte Frage NICHT mitzaehlt, siehe dortiger Kommentar zu
    "fortgesetzt"). Alle danach gestellten Fragen/Antworten werden verworfen,
    der Aufrufer haengt die bearbeitete Antwort selbst wieder an (per _zug()) -
    das genuegt, damit der Architekt beim naechsten Zug die naechste Frage
    zwangslaeufig neu stellt, ohne dass die Persona einen Sonderfall dafuer
    braucht (siehe Modul-Kommentar oben: jeder Zug bekommt ohnehin den
    kompletten Verlauf neu geschickt).
    None bei ungueltigem Index (ausserhalb des Bereichs, oder zeigt nicht auf
    eine eigene "Ich: "-Antwort) - der Aufrufer muss das als Fehler behandeln,
    NICHT den Verlauf trotzdem veraendern."""
    if bearbeite_ab < 0:
        return None
    ziel_index = bearbeite_ab + 1  # +1: synthetischer erster Verlauf-Eintrag
    if not (0 <= ziel_index < len(verlauf)) or not verlauf[ziel_index].startswith("Ich: "):
        return None
    return verlauf[:ziel_index]


def ausgangslage_erkennen(geruest: str) -> str | None:
    """Extrahiert '## Ausgangslage vor Kapitel eins' aus dem fertigen
    Geruest, falls die Architekt-Persona ihn produziert hat. Wird zu
    stand_00.md, damit Kapitel eins auf einer echten Szenerie aufbaut statt
    auf einem toten Platzhalter. None, wenn der Abschnitt fehlt - dann
    bleibt stand_00.md schlicht ungeschrieben (korrekter Normalfall)."""
    treffer = _AUSGANGSLAGE_MUSTER.search(geruest)
    if not treffer:
        return None
    inhalt = treffer.group(1).strip()
    return inhalt or None


def figuren_abschnitt_erkennen(geruest: str) -> str | None:
    """Extrahiert '## Figuren' aus dem fertigen Geruest (siehe app/api/
    architekt.py: fertig-Branch von ws_architekt) - Grundlage fuer den
    automatischen Personen-Fundus-Abgleich (app/core/fundus.py). Bewusst
    NUR die oberste '## Figuren'-Ueberschrift, nicht die gleichnamige
    '### Figuren'-Unterueberschrift unter '## Ausgangslage vor Kapitel eins'
    (die beschreibt Zustaende zu Geschichtenbeginn, keine Figurenstammdaten).
    None, wenn der Abschnitt fehlt."""
    treffer = _FIGUREN_MUSTER.search(geruest)
    if not treffer:
        return None
    inhalt = treffer.group(1).strip()
    return inhalt or None


def transkript_erzeugen(verlauf: list[str]) -> str:
    """Baut aus dem internen Verlauf ("Ich: ..."/"Du: ..." - die Perspektive,
    aus der die Persona angesprochen wird) ein lesbares Markdown-Protokoll
    des gesamten Architekten-Gespraechs, fuer spaetere Referenz im Projekt
    (siehe app/api/architekt.py - wird bei erfolgreichem Abschluss als
    projekt/architekten_gespraech.md gespeichert)."""
    zeilen = [
        "# Architekten-Gespräch",
        "",
        f"Erzeugt: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
    ]
    for eintrag in verlauf:
        if eintrag.startswith("Ich: "):
            zeilen.append(f"**Nutzer:** {eintrag[len('Ich: '):]}")
        elif eintrag.startswith("Du: "):
            zeilen.append(f"**Architekt:** {eintrag[len('Du: '):]}")
        else:
            zeilen.append(eintrag)
        zeilen.append("")
    return "\n".join(zeilen).rstrip() + "\n"
