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
# Zuletzt abgeschickte Randbedingungen (siehe eingabe_speichern) - damit der
# Nutzer sie beim nächsten Öffnen des Overlays nicht neu tippen muss, wenn ein
# Lauf fehlschlug/abgebrochen wurde. Analog zu app/core/analysator.py:
# analyse_speichern, das den importierten Rohtext dauerhaft sichert.
GERUEST_KI_EINGABE_DATEINAME = "geruest_ki_eingabe.json"

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
# System-Prompt (Spez. Kapitel 5, gestrafft) - bewusst KOMPLETT STATISCH:
# alle variablen Angaben (kapitelanzahl, zielwortzahl, sprache, ...) stehen im
# User-JSON (siehe randbedingungen_json), NICHT hier. Dadurch ist der
# System-Prompt über alle Aufrufe identisch und Ollama kann den KV-Cache-
# Präfix wiederverwenden - "neu würfeln" spart sich fast den kompletten
# Prefill. Die Struktur wird zusätzlich per JSON-Schema erzwungen (siehe
# antwort_schema), deshalb hier nur ein KURZES 1-Kapitel-Beispiel für Ton
# und Feld-Dichte statt der vollen Formatvorgabe.
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """Du bist Dramaturg für die Software „GeschichtenErzähler". Du entwirfst aus
wenigen Randbedingungen (im JSON der Nutzernachricht) ein vollständiges
Kapitel-Gerüst. Du schreibst noch keine Prosa, sondern planst.

Erzeuge genau so viele Kapitel wie im Feld "kapitelanzahl" angegeben,
fortlaufend nummeriert ab 1. Alle Texte auf der Sprache aus dem Feld
"sprache" (Standard Deutsch); Eigennamen bleiben im Original.

Pro Kapitel:
- titel: sprechender Untertitel
- ort: ein KONKRETER, benannter Schauplatz des Settings (bei Hogwarts z.B.
  Bibliothek, Astronomieturm, Raum der Wünsche, Große Halle, Kerker,
  Gewächshäuser), keine vage Umschreibung wie "ein verlassener Flügel".
  Nicht zwei Kapitel hintereinander am selben Ort. Ortswechsel im Kapitel:
  "A; dann B".
- zielwortzahl: der Wert aus "zielwortzahl_pro_kapitel", ±30 % erlaubt
- anwesende_figuren: die im Kapitel auftretenden Figuren
- vergangene_zeit: erzählte Zeit seit Ende des Vorkapitels, z.B. "zwei Wochen
  später" - PFLICHT ab Kapitel 2, nur bei Kapitel 1 leer
- ereignis: 3-5 vollständige Sätze mit der KONKRETEN Handlung des Kapitels -
  wer tut was, wo, warum; nenne den Zeitabstand zum Vorkapitel; begründe jeden
  Ortswechsel. KEIN Stichwort, KEINE Zusammenfassung in einem Halbsatz.
- funktion_im_spannungsbogen: AUSSCHLIESSLICH genau eines dieser sechs Wörter,
  nichts sonst, kein Satz, keine Erklärung: Exposition | Erregendes Moment |
  Steigende Handlung | Höhepunkt/Peripetie | Fallende Handlung |
  Auflösung/Lösung
- stand_der_liebeshandlung: 1-2 Sätze, entwickelt sich von Kapitel zu Kapitel;
  "entfällt" bei Geschichten ohne Liebeshandlung
- zustand_am_kapitelende: 1-2 Sätze mit dem Haken ins nächste Kapitel

Dramaturgie:
- Spannungsbogen-Stufen in natürlicher Reihenfolge; Höhepunkt bei ca. 75 %
  der Kapitel; "Steigende Handlung" trägt den Mittelteil und darf mehrfach
  vorkommen.
- Kapitel 1 stellt alle Hauptfiguren vor. Das letzte Kapitel greift ein Motiv
  aus Kapitel 1 wieder auf und löst den Kernkonflikt vollständig - kein
  offener Cliffhanger.
- Setting und Kanon (Feld "setting") einhalten; bekannte Orte/Figuren
  namentlich nutzen, nichts erfinden, was bekannten Fakten widerspricht.
- Explizite Intimität nur zwischen eindeutig volljährigen Figuren. Sind
  Beteiligte minderjährig, endet die Liebeshandlung spätestens beim Kuss -
  auch wenn "schluss" weiter geht; vermerke die Anpassung in "zeitlinie_kurz".
- Alles unter "tabus" wird ausgelassen.

zeitlinie_kurz: ein Satz pro Kapitel - wann es spielt, wie groß der Abstand
zum Vorkapitel ist.

Halte alle Felder knapp und stichwortartig - das ist ein Plan, keine
Erzählung. Antworte ausschließlich mit dem JSON-Objekt.

Beispiel für Ton und Feld-Dichte (ein Kapitel, Harry-Potter-Setting):
{
  "nummer": 1,
  "titel": "Zwei Hände an einem Buch",
  "ort": "Bibliothek von Hogwarts; dann Lesetisch am Fenster",
  "zielwortzahl": 1500,
  "anwesende_figuren": ["Daniel", "Hermine Granger", "Madam Pince"],
  "vergangene_zeit": "",
  "ereignis": "Zweiter Septemberabend 1995. Daniel und Hermine greifen gleichzeitig nach dem einzigen Exemplar eines Fachbuchs; höflicher Streit, wer es dringender braucht. Daniel schlägt vor, es zu teilen. Zwei Stunden am Fenstertisch, nur über das Buch - beide merken, dass der andere genauso denkt wie man selbst. Vorstellung Daniels: muggelstämmig, Einzelgänger, kennt jede Regalreihe.",
  "funktion_im_spannungsbogen": "Exposition",
  "stand_der_liebeshandlung": "Fremde. Gegenseitiger intellektueller Respekt, ein zweiter Blick beim Auseinandergehen.",
  "zustand_am_kapitelende": "Madam Pince schließt. Daniel legt einen Zettel ins Buch: Gleicher Tisch am Donnerstag? Hermine nimmt ihn mit, statt ihn wegzuwerfen."
}
"""


def system_prompt() -> str:
    return SYSTEM_PROMPT


# Ollama-JSON-Schema als `format`-Wert (statt des schwächeren format="json"):
# erzwingt die exakte Struktur UND per minItems/maxItems die exakte
# Kapitelanzahl - das Modell kann nicht mehr ausufern (Hauptgrund für die
# 30-Minuten-Läufe im ersten Test) und liefert kaum noch ungültiges JSON.
_KAPITEL_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "nummer": {"type": "integer"},
        "titel": {"type": "string"},
        "ort": {"type": "string"},
        "zielwortzahl": {"type": "integer"},
        "anwesende_figuren": {"type": "array", "items": {"type": "string"}},
        "vergangene_zeit": {"type": "string"},
        "ereignis": {"type": "string"},
        # enum statt freiem String: gemma4 hat sonst einen ganzen Absatz
        # Analyse in dieses Feld geschrieben statt einer der sechs Kategorien
        # (Live-Test 2026-09-08). Die "Eigene Angabe"-Freiheit der Spezifikation
        # entfällt damit für den KI-Erstentwurf - der Nutzer kann den Wert im
        # KapitelplanEditor immer noch auf Freitext umstellen.
        "funktion_im_spannungsbogen": {
            "type": "string",
            "enum": list(FUNKTION_IM_SPANNUNGSBOGEN_OPTIONEN),
        },
        "stand_der_liebeshandlung": {"type": "string"},
        "zustand_am_kapitelende": {"type": "string"},
    },
    "required": [
        "nummer", "titel", "ort", "anwesende_figuren", "ereignis",
        "funktion_im_spannungsbogen", "stand_der_liebeshandlung", "zustand_am_kapitelende",
    ],
}


def antwort_schema(kapitelanzahl: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "titel_der_geschichte": {"type": "string"},
            "zeitlinie_kurz": {"type": "string"},
            "kapitel": {
                "type": "array",
                "items": _KAPITEL_ITEM_SCHEMA,
                "minItems": kapitelanzahl,
                "maxItems": kapitelanzahl,
            },
        },
        "required": ["titel_der_geschichte", "kapitel"],
    }


def num_ctx_fuer(kapitelanzahl: int) -> int:
    """Dynamische Kontextgröße: System-Prompt (~900 Token) + User-JSON +
    Ausgabe (~250-350 Token/Kapitel) - auf das nächste Vielfache von 2048
    aufgerundet, gedeckelt bei 16384. CPU-Prefill auf Athene skaliert mit der
    ALLOZIERTEN Größe, nicht nur der genutzten (siehe rollen.py:analysator)."""
    grob = 3072 + kapitelanzahl * 1024
    aufgerundet = ((grob + 2047) // 2048) * 2048
    return max(6144, min(16384, aufgerundet))


def num_predict_fuer(kapitelanzahl: int) -> int:
    """Obergrenze für die Ausgabe - großzügig, aber nicht unbegrenzt (ein
    Runaway war die Hauptursache der 30-Minuten-Läufe)."""
    return min(8192, 768 + kapitelanzahl * 512)


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


def eingabe_datei(projekt_root: Path) -> Path:
    return projekt_root / "projekt" / GERUEST_KI_EINGABE_DATEINAME


def eingabe_speichern(projekt_root: Path, anfrage: dict) -> None:
    """Sichert die abgeschickten Randbedingungen, BEVOR der (lang laufende,
    evtl. fehlschlagende) Entwurf startet - so gehen die Formular-Eingaben
    nie verloren, auch wenn der Lauf abbricht oder das Overlay geschlossen
    wird."""
    pfad = eingabe_datei(projekt_root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(anfrage, ensure_ascii=False, indent=2), encoding="utf-8")


def eingabe_lesen(projekt_root: Path) -> dict | None:
    pfad = eingabe_datei(projekt_root)
    if not pfad.exists():
        return None
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


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
