"""KI entwirft das Gerüst aus wenigen Randbedingungen des Nutzers (siehe
ToDo.md "KI designt Gerüst aus ein paar Randbedingungen" und die Spezifikation
GeschichtenErzaehler_KI-Geruest_Spezifikation.md).

Vierter Weg zu einem Story-Gerüst neben Architekten-Interview, "Gerüst selbst
schreiben" und Analysator-Import: Der Nutzer füllt ein kurzes Formular
(Prämisse + Kapitelanzahl Pflicht, Rest optional), die KI liefert in EINEM
Aufruf einen kompletten Kapitelplan-Erstentwurf. Danach ist es ein ganz
normales, vom Nutzer editierbares Gerüst - kein eigenes Datenmodell.

Framework-frei wie app/core/architekt.py / app/core/analysator.py - die
Orchestrierung (Ollama-Aufruf, Hintergrund-Task, Status-Polling) liegt in
app/api/geruest_ki.py.

Aufteilung der Arbeit:
- Die KI liefert NUR das flache Ausgabe-JSON aus Spez. Kapitel 3 (Titel der
  Geschichte, Zeitlinie, Kapitelliste). Das hält die Modell-Aufgabe klein und
  stabil (format="json").
- Rahmen / Figuren / Konflikt / Regeln / Ausgangslage werden hier
  DETERMINISTISCH aus den Randbedingungen zusammengebaut (analog
  app/core/analysator.py:geruest_zusammenbauen und
  frontend/src/utils/geruestVorlage.ts:leeresGeruestSkelett). Nur so sind die
  wörtlichen Pflicht-Marker garantiert, auf die app/core/geruest.py angewiesen
  ist ("Jahr", "Jugendschutz-Stufe:", "Automatische Fortsetzung:").
- Das Kapitelplan-Bullet-Format ist 1:1 identisch zu
  frontend/src/utils/kapitelplan.ts:kapitelBlockSerialisieren bzw.
  app/core/analysator.py:kapitel_block_bauen, damit das Ergebnis im
  KapitelplanEditor normal als Kapitel-Karte editierbar ist.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from app.core import analysator as an

GERUEST_KI_STATUS_DATEINAME = "geruest_ki_status.json"

# Obergrenze wie im Formular (siehe app/schemas.py:KiGeruestStartAnfrage und
# der Spezifikation Kapitel 2: "kapitelanzahl int (1-30)").
MAX_KAPITELANZAHL = 30

STANDARD_ZIELWORTZAHL = 1500

# Exakt die sechs Werte des Dropdowns im Frontend
# (frontend/src/utils/kapitelplan.ts:FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN) und
# der Autor-Persona (app/core/epoche.py:autor_vorlage) - ein von der KI
# gelieferter unbekannter Wert wird NICHT verworfen, sondern roh übernommen
# (der KapitelplanEditor zeigt ihn dann als "Eigene Angabe").
FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN = (
    "Exposition",
    "Erregendes Moment",
    "Steigende Handlung",
    "Höhepunkt/Peripetie",
    "Fallende Handlung",
    "Auflösung/Lösung",
)

JUGENDSCHUTZ_ANZEIGE = {"voll": "Voll", "angedeutet": "Angedeutet", "jugendfrei": "Jugendfrei"}


# --------------------------------------------------------------------------
# Eingabe: Randbedingungen des Nutzers
# --------------------------------------------------------------------------

@dataclass
class Figur:
    name: str = ""
    alter: str = ""
    rolle: str = ""
    kurzbeschreibung: str = ""


@dataclass
class Randbedingungen:
    """Formular-Eingabe (Spez. Kapitel 2) plus zwei eigene Felder (`jahr`,
    `jugendschutz_stufe`), die die Spez. der App überlässt, die aber für ein
    funktionierendes geruest.md gebraucht werden."""
    praemisse: str
    kapitelanzahl: int
    setting: str = ""
    zielwortzahl_pro_kapitel: int = STANDARD_ZIELWORTZAHL
    figuren: list[Figur] = field(default_factory=list)
    genre: str = ""
    verlauf: str = ""
    konflikt: str = ""
    dramatik: str = ""  # "niedrig" | "mittel" | "hoch" | ""
    zeitraum: str = ""
    schluss: str = ""
    tabus: str = ""
    sprache: str = "Deutsch"
    jahr: str = ""  # vierstellig, optional
    jugendschutz_stufe: str = "voll"  # "voll" | "angedeutet" | "jugendfrei"


def randbedingungen_json(rb: Randbedingungen) -> str:
    """User-Nachricht an die Rolle 'geruest_dramaturg' - exakt das JSON-Format
    aus Spez. Kapitel 2 (die KI bekommt SYSTEM_PROMPT als System-Nachricht)."""
    daten = {
        "setting": rb.setting.strip(),
        "kapitelanzahl": rb.kapitelanzahl,
        "zielwortzahl_pro_kapitel": rb.zielwortzahl_pro_kapitel,
        "figuren": [
            {
                "name": f.name.strip(),
                "alter": f.alter.strip(),
                "rolle": f.rolle.strip(),
                "kurzbeschreibung": f.kurzbeschreibung.strip(),
            }
            for f in rb.figuren
            if f.name.strip()
        ],
        "praemisse": rb.praemisse.strip(),
        "genre": rb.genre.strip(),
        "verlauf": rb.verlauf.strip(),
        "konflikt": rb.konflikt.strip(),
        "dramatik": rb.dramatik.strip(),
        "zeitraum": rb.zeitraum.strip(),
        "schluss": rb.schluss.strip(),
        "tabus": rb.tabus.strip(),
        "sprache": rb.sprache.strip() or "Deutsch",
    }
    return json.dumps(daten, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# System-Prompt (Spez. Kapitel 5 + gekürzter Few-Shot aus Kapitel 7)
# --------------------------------------------------------------------------

# Fester String im Modul (epochenunabhängig, wie geruest.py:COVER_PROMPT_SYSTEM).
# {{...}}-Platzhalter werden in system_prompt() ersetzt.
_SYSTEM_PROMPT_VORLAGE = """Du bist Dramaturg für die Software „GeschichtenErzähler". Deine Aufgabe ist es,
aus wenigen Randbedingungen ein vollständiges Kapitel-Gerüst für eine Geschichte
zu entwerfen. Du schreibst noch keine Prosa, sondern planst.

Erzeuge genau {{kapitelanzahl}} Kapitel.

Für jedes Kapitel füllst du folgende Felder:
- nummer: fortlaufend ab 1
- titel: ein sprechender Untertitel
- ort: ein konkreter Schauplatz (bei Wechsel innerhalb des Kapitels: "A; dann B")
- zielwortzahl: Standard {{zielwortzahl_pro_kapitel}}, ±30 % erlaubt
- anwesende_figuren: Liste der Figuren, die im Kapitel auftreten
- vergangene_zeit: wie viel erzählte Zeit seit dem Ende des vorigen Kapitels
  vergeht (z.B. "drei Wochen später"); bei Kapitel 1 leer lassen
- ereignis: 3-8 Sätze, was passiert und warum; nenne immer den Zeitabstand zum
  vorherigen Kapitel; begründe jeden Ortswechsel
- funktion_im_spannungsbogen: genau einer dieser Werte -
  "Exposition", "Erregendes Moment", "Steigende Handlung", "Höhepunkt/Peripetie",
  "Fallende Handlung", "Auflösung/Lösung" - oder "Eigene Angabe: <Text>"
- stand_der_liebeshandlung: 1-3 Sätze; muss sich von Kapitel zu Kapitel
  entwickeln; "entfällt", wenn die Geschichte keine Liebeshandlung hat
- zustand_am_kapitelende: 1-3 Sätze mit dem Haken ins nächste Kapitel

Regeln:
1. Verteile die Spannungsbogen-Stufen in ihrer natürlichen Reihenfolge; der
   Höhepunkt liegt bei etwa 75 % der Kapitel; "Steigende Handlung" trägt den
   Mittelteil und darf mehrfach vorkommen.
2. Kapitel 1 stellt alle Hauptfiguren vor. Das letzte Kapitel greift ein Motiv
   aus Kapitel 1 wieder auf und löst den Kernkonflikt vollständig (kein
   offener Cliffhanger).
3. Halte dich an das Setting und seinen Kanon; erfinde nichts, was bekannten
   Fakten des Settings widerspricht. Nutze Orte und Figuren des Settings.
4. Explizite Intimität nur zwischen eindeutig volljährigen Figuren. Sind
   beteiligte Figuren minderjährig, endet die Liebeshandlung spätestens beim
   Kuss - auch wenn der gewünschte Schluss weiter geht. Vermerke die Anpassung
   in "zeitlinie_kurz".
5. Lasse alles aus, was unter "tabus" steht.
6. Schreibe alle Texte auf {{sprache}}. Eigennamen bleiben im Original.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt dieser Form, ohne Erklärungen,
ohne Markdown, ohne Codeblock:

{
  "titel_der_geschichte": "...",
  "zeitlinie_kurz": "ein Satz pro Kapitel: wann es spielt, wie groß der Abstand zum vorigen Kapitel ist",
  "kapitel": [
    {
      "nummer": 1,
      "titel": "...",
      "ort": "...",
      "zielwortzahl": {{zielwortzahl_pro_kapitel}},
      "anwesende_figuren": ["..."],
      "vergangene_zeit": "",
      "ereignis": "...",
      "funktion_im_spannungsbogen": "...",
      "stand_der_liebeshandlung": "...",
      "zustand_am_kapitelende": "..."
    }
  ]
}

Beispiel für die erwartete Form (nur die ersten beiden Kapitel eines
8-Kapitel-Gerüsts, Harry-Potter-Setting, Romantik):

{
  "titel_der_geschichte": "Gleicher Tisch",
  "zeitlinie_kurz": "Schuljahr 1995/96 in Hogwarts. Kap. 1 Anfang September; Kap. 2 Ende September (+3 Wochen); ...",
  "kapitel": [
    {
      "nummer": 1,
      "titel": "Zwei Hände an einem Buch",
      "ort": "Bibliothek von Hogwarts, Regal für Arithmantik; dann Lesetisch am Fenster",
      "zielwortzahl": 1500,
      "anwesende_figuren": ["Daniel", "Hermine Granger", "Madam Pince"],
      "vergangene_zeit": "",
      "ereignis": "Zweiter Septemberabend 1995. Daniel und Hermine greifen im selben Moment nach dem einzigen Exemplar eines Fachbuchs. Höflicher Streit, wer es dringender braucht; Daniel schlägt vor, es zu teilen. Zwei Stunden am Fenstertisch, nur über das Buch, doch beide merken, dass der andere genauso denkt wie man selbst. Vorstellung Daniels: muggelstämmig, Einzelgänger, kennt jede Regalreihe. Hermine findet hier die erste ruhige Stunde des Jahres.",
      "funktion_im_spannungsbogen": "Exposition",
      "stand_der_liebeshandlung": "Fremde. Gegenseitiger intellektueller Respekt, ein zweiter Blick beim Auseinandergehen.",
      "zustand_am_kapitelende": "Madam Pince schließt. Daniel legt einen Zettel ins Buch: „Gleicher Tisch am Donnerstag?" Hermine nimmt den Zettel mit, statt ihn wegzuwerfen."
    },
    {
      "nummer": 2,
      "titel": "Donnerstagabende",
      "ort": "Fenstertisch in der Bibliothek; dann Korridore zu den Türmen",
      "zielwortzahl": 1500,
      "anwesende_figuren": ["Daniel", "Hermine Granger", "Ron Weasley", "Harry Potter"],
      "vergangene_zeit": "drei Wochen später, Ende September",
      "ereignis": "Aus dem geteilten Buch ist ein fester Donnerstagstermin geworden. Hermine findet einen Fehler in Daniels Übersetzung, den er übersehen hat - er ist nicht gekränkt, sondern begeistert, und genau das unterscheidet ihn für sie von anderen. Ron und Harry holen Hermine ab und beäugen Daniel misstrauisch.",
      "funktion_im_spannungsbogen": "Erregendes Moment",
      "stand_der_liebeshandlung": "Studienfreunde. Sie freut sich auf Donnerstag mehr, als sie zugeben würde; er merkt, dass er sich für die Abende umzieht.",
      "zustand_am_kapitelende": "Hermine lädt Daniel ein, am Samstag „nur zum Zuhören" mitzukommen."
    }
  ]
}
"""


def system_prompt(rb: Randbedingungen) -> str:
    return (
        _SYSTEM_PROMPT_VORLAGE
        .replace("{{kapitelanzahl}}", str(rb.kapitelanzahl))
        .replace("{{zielwortzahl_pro_kapitel}}", str(rb.zielwortzahl_pro_kapitel))
        .replace("{{sprache}}", rb.sprache.strip() or "Deutsch")
    )


# --------------------------------------------------------------------------
# Ausgabe: LLM-Antwort-Schema (Spez. Kapitel 3)
# --------------------------------------------------------------------------

class KiKapitel(BaseModel):
    nummer: int = 0
    titel: str = ""
    ort: str = ""
    zielwortzahl: int = 0
    anwesende_figuren: list[str] = []
    # Spez. Kapitel 3 faltet den Zeitabstand ins Feld "ereignis"; unser
    # KapitelplanEditor hat aber ein eigenes Feld dafür - deshalb hier separat
    # abgefragt (optional, siehe system_prompt()).
    vergangene_zeit: str = ""
    ereignis: str = ""
    funktion_im_spannungsbogen: str = ""
    stand_der_liebeshandlung: str = ""
    zustand_am_kapitelende: str = ""


class KiGeruestAntwortLLM(BaseModel):
    titel_der_geschichte: str = ""
    zeitlinie_kurz: str = ""
    kapitel: list[KiKapitel] = []


@dataclass
class ValidierungsErgebnis:
    antwort: KiGeruestAntwortLLM
    hinweise: list[str]


def antwort_validieren(antwort_text: str, rb: Randbedingungen) -> ValidierungsErgebnis:
    """Liest die (rohe) JSON-Antwort der Rolle 'geruest_dramaturg' und bringt
    sie auf einen konsistenten Stand (Spez. Kapitel 8):
    - JSON parsen; bei Fehler ValidationError durchreichen (der Aufrufer macht
      genau EINEN Retry mit dem Hinweis "nur JSON").
    - Kapitel fortlaufend ab 1 neu nummerieren (nicht dem Modell-Feld trauen).
    - zu viele Kapitel: hinten abschneiden. Zu wenige: behalten + Hinweis.
    - unbekannte funktion_im_spannungsbogen: roh übernehmen (KapitelplanEditor
      zeigt sie als "Eigene Angabe").
    - fehlende/ungültige zielwortzahl: auf den Formular-Standard setzen.

    `hinweise` landet im Fortschritts-Log des Hintergrund-Laufs, blockiert
    aber nichts."""
    antwort = KiGeruestAntwortLLM.model_validate_json(antwort_text)
    hinweise: list[str] = []

    kapitel = list(antwort.kapitel)
    if not kapitel:
        raise ValueError("Die KI-Antwort enthielt keine Kapitel.")

    if len(kapitel) > rb.kapitelanzahl:
        hinweise.append(
            f"KI lieferte {len(kapitel)} Kapitel, {rb.kapitelanzahl} angefordert - "
            f"überzählige am Ende entfernt."
        )
        kapitel = kapitel[: rb.kapitelanzahl]
    elif len(kapitel) < rb.kapitelanzahl:
        hinweise.append(
            f"KI lieferte nur {len(kapitel)} von {rb.kapitelanzahl} Kapiteln - "
            f"bitte im Gerüst-Editor ergänzen."
        )

    bekannte = {w.lower() for w in FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN}
    for i, k in enumerate(kapitel, start=1):
        k.nummer = i
        if not k.zielwortzahl or k.zielwortzahl <= 0:
            k.zielwortzahl = rb.zielwortzahl_pro_kapitel
        wert = k.funktion_im_spannungsbogen.strip()
        # "Eigene Angabe: X" -> reiner Text X (der Editor erkennt jeden nicht
        # gelisteten Wert selbst als Freitext).
        eigen = re.match(r"(?i)^eigene angabe\s*:\s*(.+)$", wert)
        if eigen:
            k.funktion_im_spannungsbogen = eigen.group(1).strip()
        elif wert and wert.lower() not in bekannte:
            hinweise.append(
                f"Kapitel {i}: unbekannte Spannungsbogen-Funktion '{wert}' als Freitext übernommen."
            )

    antwort.kapitel = kapitel
    if not antwort.titel_der_geschichte.strip():
        antwort.titel_der_geschichte = "[Arbeitstitel]"
        hinweise.append("KI lieferte keinen Titel - Platzhalter '[Arbeitstitel]' gesetzt.")
    return ValidierungsErgebnis(antwort=antwort, hinweise=hinweise)


# --------------------------------------------------------------------------
# Zusammenbau des kompletten geruest.md
# --------------------------------------------------------------------------

def _figuren_block(figuren: list[Figur]) -> str:
    """'## Figuren'-Bullet-Liste aus den Formular-Figuren - Format lose an der
    Architekt-Persona orientiert (siehe
    frontend/src/utils/geruestVorlage.ts). Leer -> eine Platzhalter-Zeile,
    damit der Nutzer sieht, wo Figuren hingehören."""
    if not figuren:
        return (
            "*   **[Name]:** Alter: [Zahl]. [Rang/Titel/Stand]: [...]. Ziel: [...]. "
            "Größte Angst: [...]. Geheimnis: [...]. Entwicklungsbogen: [...]."
        )
    zeilen = []
    for f in figuren:
        if not f.name.strip():
            continue
        teile = []
        if f.alter.strip():
            teile.append(f"Alter: {f.alter.strip()}")
        if f.rolle.strip():
            teile.append(f.rolle.strip())
        if f.kurzbeschreibung.strip():
            teile.append(f.kurzbeschreibung.strip())
        rest = ". ".join(teile)
        zeilen.append(f"*   **{f.name.strip()}:** {rest}".rstrip())
    return "\n".join(zeilen) or "*   **[Name]:** [...]"


def _kapitel_block(k: KiKapitel) -> str:
    """EIN '## Kapitelplan'-Eintrag im Bullet-Format von
    frontend/src/utils/kapitelplan.ts:kapitelBlockSerialisieren (identisch zu
    app/core/analysator.py:kapitel_block_bauen, plus 'Vergangene Zeit')."""
    figuren = ", ".join(x.strip() for x in k.anwesende_figuren if x.strip())
    ziel = max(100, round(k.zielwortzahl / 50) * 50)
    return "\n".join([
        f"*   **Kapitel {an.zahlwort(k.nummer)}: {k.titel.strip()}**",
        f"    *   Vergangene Zeit: {k.vergangene_zeit.strip()}",
        f"    *   Ort: {k.ort.strip()}",
        f"    *   Anwesende Figuren: {figuren}",
        f"    *   Ereignis: {k.ereignis.strip()}",
        f"    *   Zielwortzahl: ca. {ziel} Wörter.",
        f"    *   Funktion im Spannungsbogen: {k.funktion_im_spannungsbogen.strip()}",
        f"    *   Stand der Liebeshandlung: {k.stand_der_liebeshandlung.strip()}",
        f"    *   Zustand am Kapitelende: {k.zustand_am_kapitelende.strip()}",
    ])


def _ausgangslage(antwort: KiGeruestAntwortLLM) -> str:
    """Kurzer, deterministisch aus Kapitel 1 gebauter Absatz - wird von
    app/core/architekt.py:ausgangslage_erkennen() zu stand_00.md (analog
    app/api/analysator.py:_analysieren_lauf)."""
    if not antwort.kapitel:
        return ""
    k1 = antwort.kapitel[0]
    figuren = ", ".join(x.strip() for x in k1.anwesende_figuren if x.strip())
    teile = []
    if k1.ort.strip():
        teile.append(f"Schauplatz zu Beginn: {k1.ort.strip()}.")
    if figuren:
        teile.append(f"Anwesend: {figuren}.")
    teile.append("Von der KI aus dem ersten Kapitel abgeleitet - bitte prüfen und ausschmücken.")
    return " ".join(teile)


def geruest_zusammenbauen(rb: Randbedingungen, antwort: KiGeruestAntwortLLM,
                           epoche_anzeigename: str = "") -> str:
    """Baut aus den Randbedingungen (deterministisch) und der KI-Antwort (nur
    Titel/Zeitlinie/Kapitel) ein vollständiges geruest.md, das über denselben
    Weg wie "Gerüst selbst schreiben" (app/api/projects.py:geruest_schreiben)
    gespeichert werden kann und g.kapitelplan_pruefen() besteht."""
    setting = rb.setting.strip() or epoche_anzeigename.strip() or "[Schauplatz]"
    jahr = rb.jahr.strip()
    zeitangabe = f"Jahr {jahr}" if re.fullmatch(r"\d{3,4}", jahr) else "Jahr [vierstellige Jahreszahl eintragen]"
    stufe = JUGENDSCHUTZ_ANZEIGE.get(rb.jugendschutz_stufe.strip().lower(), "Voll")
    titel = antwort.titel_der_geschichte.strip() or "[Arbeitstitel]"
    konflikt = rb.konflikt.strip() or "[Was will die Hauptfigur, was steht dagegen - ein Satz.]"

    kapitelplan = "\n".join(_kapitel_block(k) for k in antwort.kapitel)

    offene_punkte = ["Von der KI erzeugter Erstentwurf - bitte jedes Kapitel gegenlesen."]
    if antwort.zeitlinie_kurz.strip():
        offene_punkte.append("")
        offene_punkte.append("Zeitlinie (KI): " + antwort.zeitlinie_kurz.strip())

    abschnitte = [
        "# STORY-GERUEST",
        "## Rahmen\n"
        f"*   **Zeitangabe:** {zeitangabe}\n"
        f"*   **Ort:** {setting}\n"
        "*   **Erzählperspektive:** Dritte Person\n"
        "*   **Tempus:** Vergangenheitsform\n"
        f"*   **Jugendschutz-Stufe:** Jugendschutz-Stufe: {stufe}\n"
        "*   **Autor-Modell:** Autor-Modell: Mistral\n"
        "*   **Automatische Fortsetzung:** Automatische Fortsetzung: Aus",
        f"## Titel\n{titel}",
        f"## Figuren\n{_figuren_block(rb.figuren)}",
        f"## Konflikt\n{konflikt}",
        "## Nebenstrang\n",
        f"## Kapitelplan\n{kapitelplan}",
        f"## Ausgangslage vor Kapitel eins\n{_ausgangslage(antwort)}",
        "## Offene Punkte\n" + "\n".join(offene_punkte),
        an.regeln_text_bauen().strip(),
    ]
    return "\n\n".join(a.strip() for a in abschnitte if a.strip()) + "\n"


# --------------------------------------------------------------------------
# Status-Datei des Hintergrund-Laufs - Muster 1:1 aus
# app/core/analysator.py (bewusst eigene, einfachere Struktur: linearer
# Fortschritt, kein "Fortsetzen").
# --------------------------------------------------------------------------

def status_datei(projekt_root: Path) -> Path:
    return projekt_root / "projekt" / GERUEST_KI_STATUS_DATEINAME


def status_lesen(projekt_root: Path) -> dict:
    pfad = status_datei(projekt_root)
    if not pfad.exists():
        return {"laeuft": False, "phase": None, "log": [], "abgeschlossen": False, "fehler": None}
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"laeuft": False, "phase": None, "log": [], "abgeschlossen": False, "fehler": None}


def status_schreiben(projekt_root: Path, status: dict) -> None:
    pfad = status_datei(projekt_root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def verwaiste_laeufe_zuruecksetzen(projects_root: Path) -> int:
    """Setzt jeden geruest_ki_status.json mit laeuft=true auf laeuft=false
    (mit Fehlermeldung) zurück - EINMALIG beim Backend-Start (siehe
    app/main.py), analog app/core/analysator.py:verwaiste_laeufe_zuruecksetzen
    und aus demselben Grund (ein durch Prozessende unterbrochener
    Hintergrund-Task schreibt nie sein eigenes 'laeuft = False')."""
    zurueckgesetzt = 0
    for pfad in projects_root.rglob(GERUEST_KI_STATUS_DATEINAME):
        try:
            status = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not status.get("laeuft"):
            continue
        status["laeuft"] = False
        status["fehler"] = (
            "Der Gerüst-Entwurf wurde durch einen Backend-Neustart unterbrochen (z.B. Deploy, "
            "Absturz oder Server-Neustart) - bitte erneut starten."
        )
        try:
            pfad.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            continue
        zurueckgesetzt += 1
    return zurueckgesetzt
