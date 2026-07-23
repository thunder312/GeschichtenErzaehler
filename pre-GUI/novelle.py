#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novelle.py - Pipeline fuer historische Kurzgeschichten mit lokalen Ollama-Modellen

Weg A: spricht Ollama direkt an, ohne Open WebUI.
Nur Standardbibliothek, keine Installation noetig.

Ablauf:
    ./novelle.py init                  Epoche waehlen, Projekt im aktuellen
                                        Ordner einrichten (personas/ + projekt/)
    ./novelle.py neu <Titel>           Epoche waehlen, neues Projekt in eigenem
                                        Ordner anlegen. Das Skript wird nur
                                        VERKNUEPFT (Symlink), nicht kopiert -
                                        es gibt nur eine echte novelle.py.
                                        Der Titel darf Leerzeichen und Umlaute
                                        enthalten, z.B.
                                        ./novelle.py neu Der Markt von Rothenfeld
                                        wird zu Ordner 'Der-Markt-von-Rothenfeld'.
                                        Bestehendes Projekt im aktuellen Ordner
                                        bleibt unberuehrt.
    ./novelle.py architekt             Gespraech mit dem Architekten (interaktiv)
    ./novelle.py epoche-erstellen       Fragebogen (kein LLM) zum Anlegen einer
                                        neuen Epoche unter epochen/. Erzeugt
                                        einen Rohentwurf, keine fertige Epoche -
                                        die Verbotsliste braucht danach noch
                                        echte Recherche. Alias: neueepoche
    ./novelle.py schreiben 3           Kapitel 3 schreiben + beide Pruefer laufen lassen
    ./novelle.py schreiben 3 "..."      Wie oben, mit einem zusaetzlichen freien
                                        Hinweis fuer NUR diesen Versuch (z.B. bei
                                        starken Kontinuitaets-Bruechen im letzten
                                        Versuch: "Maggie muss anwesend sein, keine
                                        Aufloesung durch einen Kuss")
    ./novelle.py testen 3              Kapitel 3 einmal mit Hermes, einmal mit Qwen
                                        schreiben lassen und vergleichen. Ruehrt die
                                        eigentliche kapitel_03.md NICHT an
    ./novelle.py pruefen 3             nur die Pruefer erneut laufen lassen
    ./novelle.py anwenden 3            NUR hochsichere Anachronismus-Funde mit
                                        konkretem Ersatzvorschlag automatisch
                                        einarbeiten (Sicherung als .bak).
                                        'mittel'/'gering' bleiben manuell
    ./novelle.py lektorieren 3         Grammatik/Rechtschreibung/Register korrigieren
    ./novelle.py rechtschreibung 3     Interaktiv: unbekannte Woerter einzeln
                                        durchgehen, Enter behaelt, Ersatzwort
                                        eintippen ersetzt es ueberall im Kapitel
                                        und Kapitel direkt ueberschreiben (Sicherung
                                        als .bak). Am besten NACH eigener inhaltlicher
                                        Korrektur, VOR ./novelle.py stand
    ./novelle.py stand 3               Chronist: Zustand nach dem korrigierten Kapitel 3
    ./novelle.py gesamt                Endkontrolle ueber alle Kapitel zusammen
    ./novelle.py export                alle Kapitel zu einer Datei zusammenfuegen
    ./novelle.py zusammenfassen         wie export, jederzeit manuell aufrufbar
                                        (z.B. fuer Zwischenstaende). Mit Bereich:
                                        ./novelle.py zusammenfassen 1 3
                                        fasst nur Kapitel 1 bis 3 zusammen, in
                                        projekt/zusammen_01-03.md
    ./novelle.py modelle               geladene und verfuegbare Modelle anzeigen
"""

import difflib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# KONFIGURATION - hier anpassen
# ---------------------------------------------------------------------------

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Projektverzeichnis. Relativ zum AKTUELLEN ARBEITSVERZEICHNIS (cwd), nicht
# zum Skript-Ort - das bleibt so, damit jede Geschichte ihre eigenen
# personas/ + projekt/ behaelt, auch wenn das Skript selbst zentral liegt
# (per Symlink in jedem Projektordner erreichbar).
PROJEKT = Path(os.environ.get("NOVELLE_PROJEKT", "projekt"))
PERSONAS = Path(os.environ.get("NOVELLE_PERSONAS", "personas"))

# Die eigentliche Skriptdatei, ueber Symlinks hinweg aufgeloest. Wird
# ausschliesslich fuer den Zugriff auf die GETEILTE Vorlagen-Bibliothek
# verwendet (epochen/ und die epochenlosen Basis-Personas), NICHT fuer
# PROJEKT/PERSONAS oben - die bleiben bewusst cwd-relativ.
EIGENE_DATEI = Path(__file__).resolve()
SKRIPT_ORDNER = EIGENE_DATEI.parent
EPOCHEN_ORDNER = Path(os.environ.get("NOVELLE_EPOCHEN", str(SKRIPT_ORDNER / "epochen")))
GEMEINSAME_PERSONAS_ORDNER = Path(os.environ.get(
    "NOVELLE_GEMEINSAME_PERSONAS", str(SKRIPT_ORDNER / "personas")))

# Diese vier Rollen sind epochenlos und werden bei "init"/"neu" unveraendert
# aus GEMEINSAME_PERSONAS_ORDNER kopiert.
GEMEINSAME_PERSONA_DATEIEN = (
    "chronist.txt", "pruefer_kontinuitaet.txt",
    "lektor.txt", "anachronismen_korrektur.txt",
)
# Diese drei kommen aus dem gewaehlten Unterordner von epochen/.
EPOCHE_PERSONA_DATEIEN = ("architekt.txt", "autor.txt", "pruefer_anachronismus.txt")

# Wie lange Ollama ein Modell nach dem Aufruf geladen haelt.
# Hoch setzen spart das Nachladen zwischen den Rollen.
KEEP_ALIVE = "30m"

# Je Rolle: Modell, Parameter, Denkmodus.
# num_predict entspricht max_tokens.
ROLLEN = {
    "architekt": {
        "modell": "gemma4",
        "think": True,
        "optionen": {
            "temperature": 0.4,
            "top_p": 0.9,
            "min_p": 0.05,
            "top_k": 40,
            "repeat_penalty": 1.05,
            "repeat_last_n": 64,
            "num_ctx": 8192,
            "num_predict": 4096,   # Denkmodus an: braucht Luft ueber die
                                    # eigentliche Antwortlaenge hinaus
            "seed": 42,
        },
    },
    "autor": {
        "modell": "hermes3:8b",
        "think": False,           # hermes3 hat keinen Denkmodus, harmlos gesetzt
        "optionen": {
            "temperature": 0.70,   # von 0.85 gesenkt (22.07.2026): bei Tests mit
                                    # der kleinen 2-Kapitel-Testgeschichte fielen
                                    # wiederholt unbegruendete, im Geruest nicht
                                    # verankerte Details auf (erfundene Zeitangaben,
                                    # unpassende saisonale Bilder). Niedrigere
                                    # Temperatur soll das Modell naeher am
                                    # tatsaechlich Vorgegebenen halten. Nicht
                                    # weiter absenken ohne Not - sonst leidet die
                                    # Prosa-Lebendigkeit, die bei 0.85 bewusst
                                    # gewaehlt wurde.
            "top_p": 1.0,          # top_p aus, min_p uebernimmt die Filterung
            "min_p": 0.05,
            "top_k": 0,
            "repeat_penalty": 1.1,
            "repeat_last_n": 256,
            "num_ctx": 8192,       # Hermes3 8B ist nativ auf 8K trainiert;
                                    # ueber diese Grenze hinaus wird die
                                    # Qualitaet nicht zuverlaessig besser
            "num_predict": 4096,
            # kein seed: Prosa soll variieren
        },
    },
    "chronist": {
        "modell": "gemma4",
        "think": False,
        "optionen": {
            "temperature": 0.2,
            "top_p": 0.8,
            "min_p": 0.1,
            "top_k": 30,
            "repeat_penalty": 1.0,
            "repeat_last_n": 64,
            "num_ctx": 16384,
            "num_predict": 1024,
            "seed": 42,
        },
    },
    "anachronismus": {
        "modell": "gemma4",
        "think": True,           # schrittweises Pruefen hilft hier
        "optionen": {
            "temperature": 0.1,
            "top_p": 0.7,
            "min_p": 0.1,
            "top_k": 20,
            "repeat_penalty": 1.0,
            "repeat_last_n": 64,
            "num_ctx": 16384,
            "num_predict": 6144,   # Denkmodus verbraucht denselben Topf wie
                                    # die Antwort; bei 2048 kam wiederholt
                                    # eine leere Antwort heraus, weil das
                                    # Nachdenken das Limit allein aufbrauchte
            "seed": 42,
        },
    },
    "kontinuitaet": {
        "modell": "gemma4",
        "think": True,
        "optionen": {
            "temperature": 0.1,
            "top_p": 0.7,
            "min_p": 0.1,
            "top_k": 20,
            "repeat_penalty": 1.0,
            "repeat_last_n": 64,
            "num_ctx": 16384,
            "num_predict": 6144,   # siehe Begruendung bei "anachronismus"
            "seed": 42,
        },
    },
    "autor_qwen_test": {
        # Urspruenglich reine Vergleichsrolle fuer ./novelle.py testen <n>,
        # wird inzwischen auch produktiv verwendet, wenn der Architekt im
        # Geruest "Autor-Modell: Qwen3" hinterlegt hat (siehe
        # _autor_rolle_erkennen). Nutzt dieselbe autor.txt-Persona wie die
        # produktive Hermes-Rolle, nur mit anderem Modell und dessen eigenen
        # empfohlenen Parametern - fairer Vergleich, weil nur Modell+
        # Parameter variieren, nicht die Anweisung selbst.
        # weil nur Modell+Parameter variieren, nicht die Anweisung selbst.
        "modell": "qwen3:14b",
        "think": False,        # zwingend aus: Qwen3 ist ein Denkmodus-Modell,
                                 # und ein volles Kapitel als Antwort teilt sich
                                 # sonst denselben Token-Topf mit dem Denken -
                                 # genau das Problem, das schon einmal zu einer
                                 # leeren Antwort gefuehrt hat (siehe Lektor).
        "optionen": {
            "temperature": 0.7,     # Qwens eigene Empfehlung fuer Nicht-Denk-Modus
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
            "presence_penalty": 1.5,  # von Qwens Team explizit empfohlen
            "num_ctx": 16384,
            "num_predict": 6144,
            # kein seed: soll wie die produktive Autor-Rolle natuerlich variieren
        },
    },
    "lektor": {
        "modell": "gemma4",
        "think": False,        # Denkmodus AUS: die Antwort ist bereits der
                                 # komplette umgeschriebene Kapiteltext, oft
                                 # 1500+ Woerter. Kaeme Denkmodus dazu, teilen
                                 # sich Denken und Antwort denselben Budget-
                                 # Topf - genau das Problem, das schon einmal
                                 # zu einer leeren Antwort gefuehrt hat.
        "optionen": {
            "temperature": 0.15,
            "top_p": 0.8,
            "min_p": 0.1,
            "top_k": 30,
            "repeat_penalty": 1.0,
            "repeat_last_n": 64,
            "num_ctx": 16384,
            "num_predict": 6144,
            "seed": 42,
        },
    },
    "anachronismen_korrektur": {
        "modell": "gemma4",
        "think": False,        # gleicher Grund wie beim Lektor: voller
                                 # Kapiteltext als Antwort, kein Denkmodus-Risiko
        "optionen": {
            "temperature": 0.1,   # noch niedriger als der Lektor: hier soll
                                    # NICHTS improvisiert werden, nur exakt
                                    # das aus der Tabelle uebernommen werden
            "top_p": 0.7,
            "min_p": 0.1,
            "top_k": 20,
            "repeat_penalty": 1.0,
            "repeat_last_n": 64,
            "num_ctx": 16384,
            "num_predict": 6144,
            "seed": 42,
        },
    },
}

# Fuer den Gesamtdurchlauf ueber alle Kapitel wird der Kontext angehoben.
GESAMT_NUM_CTX = 24576
GESAMT_NUM_PREDICT = 6144

# Deutsche Zahlwoerter 1-20, weil der Architekt Kapitelnummern mal als Ziffer
# ("Kapitel 3"), mal ausgeschrieben ("Kapitel drei") formuliert.
_ZAHLWORT = {
    "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fuenf": 5, "fünf": 5,
    "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11,
    "zwoelf": 12, "zwölf": 12, "dreizehn": 13, "vierzehn": 14,
    "fuenfzehn": 15, "fünfzehn": 15, "sechzehn": 16, "siebzehn": 17,
    "achtzehn": 18, "neunzehn": 19, "zwanzig": 20,
}


def _kapitelplan_erkennen(geruest: str) -> dict:
    """Liest Kapitelnummern und Zielwortzahlen direkt aus dem Kapitelplan
    des Gerüsts, statt sie fest einzuprogrammieren. Ersetzt die frühere feste
    Tabelle, die nur zur allerersten, 6-kapitligen Testgeschichte gepasst
    hat und bei jeder anderen Kapitelzahl schlicht ins Leere lief.
    Robust gegenueber Ziffern ODER ausgeschriebenen Zahlen, aber kein Ersatz
    fuer ein festes Datenformat: bei sehr freier Formulierung des Architekten
    kann ein einzelnes Kapitel fehlen. Dann greift der bestehende Fallback
    (kein Zielwert, keine Warnung, keine automatische Fortsetzung fuer
    dieses eine Kapitel)."""
    zahlwoerter_muster = "|".join(_ZAHLWORT)
    kapitel_muster = rf"Kapitel\s+(\d{{1,2}}|{zahlwoerter_muster})\b"
    ergebnis = {}
    treffer = list(re.finditer(kapitel_muster, geruest, re.IGNORECASE))
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


def _kapitel_block_erkennen(geruest: str, gesuchte_nummer: int):
    """Liefert den vollen Textblock des EINEN gesuchten Kapitels aus dem
    echten Kapitelplan (also aus dem Block, in dem tatsaechlich eine
    Zielwortzahl steht - das unterscheidet ihn von blossen
    Kapitel-Erwaehnungen anderswo im Geruest, z.B. im Nebenstrang-Abschnitt).

    Grund fuer diese Funktion: Der Autor bekam bisher bei jedem Aufruf das
    KOMPLETTE Geruest mit allen Kapitelplaenen gleichrangig mitgeschickt.
    Bei einem 8B-Modell besteht dabei ein reales Risiko, dass es sich waehrend
    einer automatischen Fortsetzung an einer SPAETEREN Kapitel-Stufe bedient
    (z.B. eine explizite Szene aus Kapitel 4, waehrend es eigentlich Kapitel 1
    - "nur Begegnung, noch distanziert" - fortsetzen sollte). Das gezielte
    Hervorheben nur des aktuellen Kapitel-Blocks soll dieses Risiko senken,
    kann es aber nicht vollstaendig ausschliessen - das bleibt ein
    semantisches Problem, kein rein mechanisches."""
    zahlwoerter_muster = "|".join(_ZAHLWORT)
    kapitel_muster = rf"Kapitel\s+(\d{{1,2}}|{zahlwoerter_muster})\b"
    treffer = list(re.finditer(kapitel_muster, geruest, re.IGNORECASE))
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


# ---------------------------------------------------------------------------
# Ausgabe-Helfer
# ---------------------------------------------------------------------------

class F:
    """Farbcodes, deaktiviert bei Umleitung in eine Datei."""
    aktiv = sys.stderr.isatty()
    BLAU = "\033[94m" if aktiv else ""
    GRUEN = "\033[92m" if aktiv else ""
    GELB = "\033[93m" if aktiv else ""
    ROT = "\033[91m" if aktiv else ""
    GRAU = "\033[90m" if aktiv else ""
    AUS = "\033[0m" if aktiv else ""


def info(text):
    print(f"{F.BLAU}==>{F.AUS} {text}", file=sys.stderr)


def ok(text):
    print(f"{F.GRUEN} ok{F.AUS} {text}", file=sys.stderr)


def warn(text):
    print(f"{F.GELB}  ! {F.AUS}{text}", file=sys.stderr)


def fehler(text, code=1):
    print(f"{F.ROT}FEHLER{F.AUS} {text}", file=sys.stderr)
    sys.exit(code)


def woerter(text):
    return len(re.findall(r"\b\w+\b", text))


# ---------------------------------------------------------------------------
# Ollama-Anbindung
# ---------------------------------------------------------------------------

def ollama_chat(rolle, system, user, ueberschreibe=None, still=False):
    """
    Schickt eine Anfrage an /api/chat und streamt die Antwort auf stderr mit.
    Gibt den reinen Antworttext zurueck, ohne Denk-Bloecke.
    """
    if rolle not in ROLLEN:
        fehler(f"Unbekannte Rolle: {rolle}")

    cfg = ROLLEN[rolle]
    optionen = dict(cfg["optionen"])
    if ueberschreibe:
        optionen.update(ueberschreibe)

    payload = {
        "model": cfg["modell"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "think": cfg.get("think", False),
        "options": optionen,
    }

    daten = json.dumps(payload).encode("utf-8")
    anfrage = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=daten,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    info(f"{rolle} ({cfg['modell']}, num_ctx={optionen.get('num_ctx')}) "
         f"- Eingabe {woerter(system) + woerter(user)} Woerter")

    teile = []
    denk_aktiv = False
    denk_gesehen = False
    start = time.time()
    letzte_meldung = start

    try:
        with urllib.request.urlopen(anfrage, timeout=3600) as antwort:
            for zeile in antwort:
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    stueck = json.loads(zeile)
                except json.JSONDecodeError:
                    continue

                if "error" in stueck:
                    fehler(f"Ollama meldet: {stueck['error']}")

                nachricht = stueck.get("message", {})

                # Denk-Block getrennt behandeln, nicht in die Ausgabe uebernehmen
                gedanke = nachricht.get("thinking")
                if gedanke:
                    denk_gesehen = True
                    if not denk_aktiv and not still:
                        print(f"{F.GRAU}    (denkt nach", end="", file=sys.stderr,
                              flush=True)
                        denk_aktiv = True
                    if not still and time.time() - letzte_meldung > 2:
                        print(".", end="", file=sys.stderr, flush=True)
                        letzte_meldung = time.time()

                inhalt = nachricht.get("content", "")
                if inhalt:
                    if denk_aktiv and not still:
                        print(f"){F.AUS}", file=sys.stderr, flush=True)
                        denk_aktiv = False
                    teile.append(inhalt)
                    if not still:
                        print(inhalt, end="", file=sys.stderr, flush=True)

                if stueck.get("done"):
                    if not still:
                        print("", file=sys.stderr)
                    dauer = stueck.get("eval_duration", 0) / 1e9
                    anzahl = stueck.get("eval_count", 0)
                    rate = anzahl / dauer if dauer else 0
                    grund = stueck.get("done_reason", "")
                    ok(f"{anzahl} Token in {time.time() - start:.0f}s "
                       f"({rate:.1f} Token/s)")
                    if grund == "length" and denk_gesehen and not teile:
                        warn(f"Limit erreicht, waehrend das Modell noch im "
                             f"Denkmodus war ({anzahl} Token, alle fuers "
                             f"Nachdenken). Keine Antwort entstanden.")
                        warn(f"Abhilfe: num_predict fuer Rolle '{rolle}' in "
                             f"ROLLEN erhoehen, oder \"think\": False setzen.")
                    break

    except urllib.error.URLError as e:
        fehler(f"Ollama nicht erreichbar unter {OLLAMA_URL}: {e}\n"
               f"       Laeuft der Container? Bei Ollama im Docker-Netz ggf.\n"
               f"       OLLAMA_URL=http://ollama:11434 setzen.")

    text = "".join(teile).strip()
    if not text:
        fehler("Leere Antwort erhalten. Modell vorhanden? "
               "Pruefe mit: ./novelle.py modelle")
    return text


def ollama_get(pfad):
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}{pfad}", timeout=30) as a:
            return json.loads(a.read())
    except urllib.error.URLError as e:
        fehler(f"Ollama nicht erreichbar unter {OLLAMA_URL}: {e}")


# ---------------------------------------------------------------------------
# Dateizugriff
# ---------------------------------------------------------------------------

def lies(pfad, pflicht=True, ersatz=""):
    p = Path(pfad)
    if not p.exists():
        if pflicht:
            fehler(f"Datei fehlt: {p}\n"
                   f"       Fehlt das Projektgeruest? ./novelle.py init")
        return ersatz
    return p.read_text(encoding="utf-8").strip()


def schreib(pfad, text, force=False):
    p = Path(pfad)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and not force:
        sicherung = p.with_suffix(p.suffix + f".{int(time.time())}.bak")
        p.rename(sicherung)
        warn(f"Vorhandene Datei gesichert als {sicherung.name}")
    p.write_text(text + "\n", encoding="utf-8")
    ok(f"geschrieben: {p}  ({woerter(text)} Woerter)")
    return p


def persona(name):
    return lies(PERSONAS / f"{name}.txt")


def kapitel_datei(n):
    return PROJEKT / f"kapitel_{n:02d}.md"


def stand_datei(n):
    return PROJEKT / f"stand_{n:02d}.md"


def befunde_datei(n):
    return PROJEKT / f"befunde_{n:02d}.md"


# ---------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------

def _nur_erste_frage(antwort: str) -> str:
    """Der Architekt soll laut Persona nur eine Frage pro Nachricht stellen.
    Ein 8B-Modell haelt sich daran nicht zuverlaessig und packt gelegentlich
    mehrere nummerierte Fragen in eine Antwort. Dieser Filter schneidet alles
    ab der zweiten nummerierten Frage ab, damit garantiert nur eine Frage
    angezeigt wird, unabhaengig vom Modellverhalten. Wird NICHT auf das
    fertige Story-Geruest angewandt (das hat selbst nummerierte Listen,
    z.B. den Kapitelplan, die nicht faelschlich abgeschnitten werden duerfen)."""
    treffer = list(re.finditer(r"^\s*\d+\.\s+", antwort, re.MULTILINE))
    if len(treffer) < 2:
        return antwort
    grenze = treffer[1].start()
    gekuerzt = antwort[:grenze].rstrip()
    warn(f"Architekt hat {len(treffer)} Fragen auf einmal gestellt. "
         f"Nur die erste wird angezeigt, der Rest wird verworfen.")
    return gekuerzt


def _ausgangslage_erkennen(geruest: str):
    """Extrahiert den Abschnitt '## Ausgangslage vor Kapitel eins' aus dem
    fertigen Geruest, falls der Architekt ihn produziert hat. Wird zu
    stand_00.md, damit Kapitel eins auf einer echten Szenerie aufbaut statt
    auf einem toten Platzhalter. Liefert None, wenn der Abschnitt fehlt -
    dann bleibt stand_00.md schlicht ungeschrieben, und der Autor bekommt
    beim ersten Kapitel korrekt die Meldung 'kein vorheriger Stand'."""
    treffer = re.search(
        r"##\s*Ausgangslage\s+vor\s+Kapitel\s+eins\s*\n(.*?)(?=\n##\s|\Z)",
        geruest, re.IGNORECASE | re.DOTALL,
    )
    if not treffer:
        return None
    inhalt = treffer.group(1).strip()
    return inhalt or None


def _projektordner_nach_titel_umbenennen(geruest: str):
    """Versucht, den aktuellen Projektordner (das Arbeitsverzeichnis, in dem
    novelle.py gerade laeuft) nach dem Titel aus dem Geruest umzubenennen.
    Wird nur direkt nach dem Architekten-Gespraech aufgerufen, solange noch
    kein einziges Kapitel geschrieben wurde - zu einem spaeteren Zeitpunkt
    waere das riskanter, weil dann bereits Dateien in aktiver Bearbeitung
    waeren.

    Rein informell und best-effort: Schlaegt die Umbenennung fehl (z.B. weil
    der Zielordner schon existiert), wird nur gewarnt, nichts abgebrochen.
    Der Symlink auf das zentrale Skript bleibt davon unberuehrt - Symlinks
    im umbenannten Ordner funktionieren unveraendert weiter, und unter POSIX
    bleibt auch das aktuelle Arbeitsverzeichnis des laufenden Prozesses nach
    der Umbenennung gueltig (ueber den Inode verfolgt, nicht den Pfadnamen)."""
    if list(PROJEKT.glob("kapitel_*.md")):
        return  # es gibt schon Kapitel - nicht mehr automatisch umbenennen

    titel_treffer = re.search(r"##\s*Titel\s*\n+(.+)", geruest)
    if not titel_treffer:
        return
    titel = titel_treffer.group(1).strip()
    neuer_name = _ordnername_aus_titel(titel)

    aktueller_pfad = Path.cwd()
    if aktueller_pfad.name == neuer_name:
        return  # schon passend benannt

    neuer_pfad = aktueller_pfad.parent / neuer_name
    if neuer_pfad.exists():
        warn(f"Projektordner wird NICHT automatisch umbenannt: Zielname "
             f"'{neuer_name}' existiert bereits im uebergeordneten Ordner.")
        return

    try:
        aktueller_pfad.rename(neuer_pfad)
    except OSError as e:
        warn(f"Projektordner konnte nicht automatisch umbenannt werden: {e}")
        return

    ok(f"Projektordner umbenannt: '{aktueller_pfad.name}' -> '{neuer_name}'")
    info("Dein Terminal zeigt in der Eingabeaufforderung eventuell noch den "
         "alten Namen an, bis du z.B. 'cd .' eingibst oder ein neues "
         "Terminal oeffnest - das ist nur die Anzeige, der Ordner selbst "
         "ist bereits korrekt umbenannt.")


def cmd_architekt(_args):
    """Interaktives Gespraech mit dem Architekten."""
    sys_prompt = persona("architekt")
    verlauf = []
    info("Architekten-Gespraech. Leere Eingabe oder 'ende' beendet es.")
    info("Das fertige Geruest wird am Ende automatisch gespeichert.")
    print("", file=sys.stderr)

    eingabe = "Lass uns anfangen. Stelle mir die ersten Fragen."
    while True:
        verlauf.append(f"Ich: {eingabe}")
        # still=True: Streaming wird unterdrueckt, damit die Antwort erst
        # nach dem Kuerzen auf eine Frage angezeigt wird. Sonst waeren
        # mehrere Fragen schon auf dem Bildschirm, bevor der Filter greift.
        info("(Architekt denkt nach ...)")
        antwort = ollama_chat("architekt", sys_prompt, "\n\n".join(verlauf),
                               still=True)

        ist_geruest = bool(re.match(r"\s*#\s*STORY-GERUEST", antwort, re.IGNORECASE))
        if not ist_geruest:
            antwort = _nur_erste_frage(antwort)

        print(antwort, file=sys.stderr)
        verlauf.append(f"Du: {antwort}")
        print("", file=sys.stderr)

        # Das fertige Geruest ist das definierte Endsignal der Persona.
        # Sobald es erscheint, ist das Gespraech inhaltlich abgeschlossen -
        # nicht mehr auf eine weitere Eingabe warten, sondern direkt speichern.
        if ist_geruest:
            ok("Story-Geruest erkannt, Architekten-Gespraech automatisch beendet.")
            schreib(PROJEKT / "geruest.md", antwort, force=True)

            ausgangslage = _ausgangslage_erkennen(antwort)
            if ausgangslage:
                schreib(stand_datei(0),
                        "# STAND VOR KAPITEL EINS\n\n" + ausgangslage,
                        force=True)
                ok("Ausgangslage erkannt, als stand_00.md gespeichert.")
            else:
                warn("Keine 'Ausgangslage vor Kapitel eins' im Geruest gefunden. "
                     "Kapitel eins startet ohne vorherigen Stand - das ist "
                     "der korrekte Normalfall, falls die Persona diesen "
                     "Abschnitt (noch) nicht produziert.")

            _projektordner_nach_titel_umbenennen(antwort)
            break

        try:
            eingabe = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not eingabe or eingabe.lower() in ("ende", "exit", "quit"):
            break
    info("Beendet.")


def _pruefe(n, kapiteltext):
    """Beide Pruefer laufen lassen, Ergebnis als eine Datei."""
    geruest = lies(PROJEKT / "geruest.md")
    verbote = lies(PROJEKT / "verbotsliste.md")
    vorher = lies(stand_datei(n - 1), pflicht=False,
                  ersatz="(Kein vorheriger Stand vorhanden. "
                         "Dies ist das erste Kapitel.)")

    jahr = "unbekannt"
    treffer = re.search(r"\b(1[0-9]{3})\b", geruest)
    if treffer:
        jahr = treffer.group(1)
    info(f"Erkanntes Jahr aus dem Geruest: {jahr}")

    a = ollama_chat(
        "anachronismus",
        persona("pruefer_anachronismus"),
        f"JAHR: {jahr}\n\n"
        f"=== VERBOTSLISTE ===\n{verbote}\n\n"
        f"=== KAPITELTEXT ===\n{kapiteltext}",
    )

    k = ollama_chat(
        "kontinuitaet",
        persona("pruefer_kontinuitaet"),
        f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
        f"=== NEUES KAPITEL {n} ===\n{kapiteltext}",
    )

    bericht = (
        f"# Befunde zu Kapitel {n}\n\n"
        f"Erzeugt: {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"Jahr laut Geruest: {jahr}\n\n"
        f"---\n\n## Anachronismen\n\n{a}\n\n"
        f"---\n\n## Kontinuitaet und Logik\n\n{k}\n"
    )
    schreib(befunde_datei(n), bericht)


# Sehr haeufige englische Fuellwoerter. Kein Sprach-Tool, nur ein schneller
# Rauchmelder: taucht ein auffaelliger Anteil davon auf, ist das ein starkes
# Indiz fuer einen Sprachdrift ins Englische, wie er bei englisch-lastig
# trainierten Modellen (z.B. hermes3) gelegentlich vorkommt, besonders bei
# automatischen Fortsetzungs-Aufrufen.
ENGLISCHE_SIGNALWOERTER = re.compile(
    r"\b(the|and|was|were|with|his|her|that|this|they|their|had|from|"
    r"which|would|could|should|what|when|where|because|you|your)\b",
    re.IGNORECASE,
)


# Jugendschutz-Stufe: wird vom Architekten im Geruest festgehalten und bei
# jedem Kapitel als Direktive an den Autor mitgeschickt. Faellt sie im Geruest
# nicht eindeutig aus, greift der bisherige Standard ("voll") - so bleibt
# jedes Projekt, das diese Frage noch nicht kannte, im bisherigen Verhalten.
STUFE_DIREKTIVEN = {
    "voll": (
        "Content-Stufe fuer dieses Projekt: VOLL EXPLIZIT. Halte dich an die "
        "Vorgaben deiner Persona zu expliziter Erotik."
    ),
    "angedeutet": (
        "WICHTIG, Content-Stufe fuer dieses Projekt: ANGEDEUTET/ROMANTISCH. "
        "Ignoriere fuer dieses Projekt alle Anweisungen deiner Persona zu "
        "expliziten sexuellen Handlungen (Oralsex, Analsex, Fingering, "
        "detaillierte koerperliche Beschreibung des Akts). Erlaubt sind "
        "Anziehung, Naehe, Kuss, Umarmung, angedeutete Zuneigung. Ein "
        "intimer Moment darf beginnen, wird aber VOR dem eigentlichen "
        "sexuellen Akt per Szenenwechsel, Ellipse oder gedaempfter Andeutung "
        "beendet, z.B. 'Er zog sie sanft zu sich, und die Kerze verlosch.' "
        "Keine expliziten Koerperbeschreibungen sexueller Natur."
    ),
    "jugendfrei": (
        "WICHTIG, Content-Stufe fuer dieses Projekt: JUGENDFREI. Ignoriere "
        "fuer dieses Projekt VOLLSTAENDIG alle Anweisungen deiner Persona zu "
        "Erotik oder Sexualitaet. Keine koerperliche Intimitaet ueber "
        "Handhalten, eine Umarmung oder einen einzelnen, keuschen Kuss "
        "hinaus. Romantische Gefuehle duerfen thematisiert werden, aber rein "
        "emotional, nie koerperlich vertieft. Kein Bett, kein Entkleiden, "
        "keine sinnliche Beschreibung von Koerpern."
    ),
}


def _jugendschutz_stufe_erkennen(geruest: str) -> str:
    """Liest die Jugendschutz-Stufe aus dem Geruest. Unbekannt oder nicht
    gefunden -> 'voll', damit bestehende Projekte ohne diese Frage sich
    exakt wie bisher verhalten."""
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


def _autor_rolle_erkennen(geruest: str) -> str:
    """Liest aus dem Geruest, welches Modell die Geschichte schreiben soll
    (Frage im Architekten-Interview). Fehlt die Angabe (aeltere Projekte
    ohne diese Frage), gilt automatisch die bisherige Standardrolle
    ('autor', Hermes) - unveraendertes Verhalten fuer Bestandsprojekte."""
    treffer = re.search(r"Autor-Modell\s*[:\-]?\s*([A-Za-z0-9 ]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return "autor"
    wert = treffer.group(1).lower()
    if "qwen" in wert:
        return "autor_qwen_test"
    return "autor"


def _automatische_fortsetzung_aktiviert(geruest: str) -> bool:
    """Liest aus dem Geruest, ob bei zu kurzen Kapiteln automatisch
    fortgesetzt werden soll. Default: AUS, auch wenn das Feld fehlt - das
    ist bewusst der sicherere Standard. Die automatische Fortsetzung war
    wiederholt die Ursache fuer schwere Fehler (Szenensprung, doppelte
    Ueberschrift, unmotivierte neue Szenen nach einem selbst erklaerten
    Kapitelende) - ein 8B-Modell versucht beim Fortsetzen oft "auf Krampf",
    die Zielwortzahl zu erreichen, statt die Szene organisch zu Ende zu
    erzaehlen. Nur ein eindeutiges "Ein" aktiviert die Fortsetzung."""
    treffer = re.search(r"Automatische Fortsetzung\s*[:\-]?\s*([A-Za-zÄÖÜäöüß]+)",
                         geruest, re.IGNORECASE)
    if not treffer:
        return False
    wert = treffer.group(1).lower()
    return wert.startswith("ein")


def _sprachdrift_pruefen(text: str, kontext: str = "", schwelle: float = 0.03):
    gesamt = woerter(text)
    if gesamt == 0:
        return
    treffer = len(ENGLISCHE_SIGNALWOERTER.findall(text))
    anteil = treffer / gesamt
    if anteil > schwelle:
        praefix = f"{kontext}: " if kontext else ""
        warn(f"{praefix}moeglicher Sprachdrift ins Englische - {treffer} "
             f"typisch englische Woerter auf {gesamt} Woerter gesamt "
             f"({anteil:.0%}).")
        warn("Text durchlesen. Bei echtem Drift: betroffenen Abschnitt "
             "verwerfen und neu erzeugen lassen, nicht nur uebersetzen "
             "(sonst bleiben Kontinuitaetsfehler aus der Drift-Passage "
             "bestehen).")


_ICH_PRONOMEN_MUSTER = re.compile(
    r"\b(ich|mein|meine|meinen|meiner|meinem|meines|mir|mich)\b", re.IGNORECASE)


def _erzaehlperspektive_pruefen(text: str, geruest: str, kontext: str = "",
                                 schwellwert: int = 2):
    """Warnt, wenn das Geruest 'Dritte Person' vorschreibt, aber ausserhalb
    woertlicher Rede eindeutige Ich-Perspektive auftaucht (z.B. "meine Hand",
    "sagte ich"). Woertliche Rede in Anfuehrungszeichen darf natuerlich "ich"
    enthalten - das ist normale erste Person im Dialog, kein
    Perspektivwechsel der Erzaehlstimme. Deshalb wird Dialogtext vorher grob
    entfernt (deutsche „...“ und ASCII "..." Anfuehrungszeichen), bevor
    gezaehlt wird.

    Nur relevant, wenn das Geruest explizit dritte Person vorschreibt - bei
    Ich-Erzaehlungen waere das Verhalten ja korrekt und soll nicht anschlagen."""
    if not re.search(r"Dritte Person", geruest, re.IGNORECASE):
        return
    ohne_dialog = re.sub(r'„[^"“]*["“]', ' ', text)
    ohne_dialog = re.sub(r'"[^"]*"', ' ', ohne_dialog)
    treffer = _ICH_PRONOMEN_MUSTER.findall(ohne_dialog)
    if len(treffer) >= schwellwert:
        praefix = f"{kontext}: " if kontext else ""
        gefundene_woerter = ", ".join(sorted(set(w.lower() for w in treffer)))
        warn(f"{praefix}Geruest schreibt dritte Person vor, aber ausserhalb "
             f"woertlicher Rede tauchen {len(treffer)} Ich-Perspektive-Woerter "
             f"auf ({gefundene_woerter}).")
        warn("Das Kapitel ist vermutlich mitten im Text in die Ich-Perspektive "
             "gerutscht - unbedingt gegenlesen, betroffenen Abschnitt eher "
             "neu schreiben lassen als von Hand umzuformulieren.")


_FORMELL_ANREDE_MUSTER = re.compile(r"\b(Sie|Ihnen)\b")
_INFORMELL_ANREDE_MUSTER = re.compile(r"\b(du|dich|dir|dein\w*)\b")


def _anredeform_pruefen(text: str, kontext: str = ""):
    """Warnt, wenn innerhalb desselben Kapitels sowohl foermliche (Sie/Ihnen)
    als auch informelle Anrede (du/dich/dir/dein) in woertlicher Rede
    vorkommt. Nur die Anrede-Woerter INNERHALB von Anfuehrungszeichen zaehlen
    - Erzaehltext ausserhalb der woertlichen Rede enthaelt "sie" naturgemaess
    haeufig als normales Personalpronomen und waere sonst ein staendiger
    Fehlalarm.

    Ein Wechsel kann im Verlauf einer ganzen Geschichte durchaus beabsichtigt
    sein (wachsende Vertrautheit ueber mehrere Kapitel), ist aber innerhalb
    EINES Kapitels - insbesondere bei einer ersten Begegnung - meist ein
    unbeabsichtigter Ausrutscher, kein bewusster Stilmittel."""
    # Sowohl deutsche „..." als auch ASCII "..." Anfuehrungszeichen abdecken -
    # ein reiner ASCII-Abgleich uebersieht jeden Dialog, der korrekt im
    # geforderten deutschen Format geschrieben wurde (genau das ist bei einem
    # echten Testfall passiert: der Check schwieg, weil der Text brav die
    # deutschen Anfuehrungszeichen nutzte).
    dialogzeilen = re.findall(r'„([^"“]*)["“]', text)
    dialogzeilen += re.findall(r'"([^"]*)"', text)
    dialogtext = " ".join(dialogzeilen)
    foermlich = _FORMELL_ANREDE_MUSTER.findall(dialogtext)
    informell = _INFORMELL_ANREDE_MUSTER.findall(dialogtext)
    if foermlich and informell:
        praefix = f"{kontext}: " if kontext else ""
        warn(f"{praefix}Sowohl foermliche Anrede (Sie/Ihnen, {len(foermlich)}x) "
             f"als auch informelle Anrede (du/dich/dir/dein, {len(informell)}x) "
             f"in woertlicher Rede gefunden.")
        warn("Pruefen, ob der Wechsel beabsichtigt ist (z.B. wachsende "
             "Vertrautheit) oder ein unbegruendeter Ausrutscher.")


# Typische Ausweichformulierungen, mit denen kleine Modelle explizite Szenen
# durch vage Andeutung ersetzen, statt sie auszuschreiben. Kein Ersatz fuers
# Selberlesen, aber ein schneller Hinweis, wo genauer hingeschaut werden sollte.
AUSWEICH_MUSTER = [
    "sprache des samens", "sprache der liebe",
    "blumenkelch", "blumen der liebe",
    "grenzen erkundet", "grenzen erkunden",
    "verloren ineinander", "eins wurden", "eins werden",
    "neue welt", "neuer morgen brach",
    "wie die götter", "wie die goetter es vorgeschrieben",
]


def _pruefe_ausweichformulierungen(text):
    treffer = [m for m in AUSWEICH_MUSTER if m in text.lower()]
    if treffer:
        warn(f"Moegliche Ausweichformulierung(en) gefunden: {', '.join(treffer)}")
        warn("Das deutet auf ein Fade-to-black statt einer ausgefuehrten Szene "
             "hin. Kapitel lesen, nicht nur auf die Wortzahl verlassen.")


# Vokabular, das eindeutig auf explizite sexuelle Handlung hinweist. Wird nur
# geprueft, wenn die Jugendschutz-Stufe NICHT "voll" ist - dort waere es ja
# ausdruecklich erwuenscht. Bewusst auf eindeutige Begriffe beschraenkt statt
# generischer Woerter wie "steif" oder "kam", die zu viele Fehlalarme geben.
EXPLIZIT_SIGNALWOERTER = [
    "oralsex", "analsex", "cunnilingus", "fellatio", "fingering",
    "penetration", "ejakulation", "orgasmus", "erektion",
    "klitoris", "vagina", "penis", "eichel", "sperma",
    "geschlechtsteil", "schwanz", "muschi",
    "drang in sie ein", "drang tief in sie", "stiess in sie",
    "leckte zwischen ihren beinen", "saugte an ihrer klitoris",
]


def _explizitheit_pruefen(text: str, stufe: str, kontext: str = ""):
    """Warnt, wenn trotz einer reduzierten Jugendschutz-Stufe eindeutig
    explizites Vokabular auftaucht. Kein Ersatz fuers Gegenlesen, aber ein
    schneller erster Hinweis, ob sich Autor und Prompt tatsaechlich an die
    Stufe gehalten haben. Nutzt Wortgrenzen (\\b), damit z.B. "eichel" nicht
    faelschlich in "streichelte" anschlaegt."""
    if stufe == "voll":
        return
    text_klein = text.lower()
    treffer = [w for w in EXPLIZIT_SIGNALWOERTER
               if re.search(r"\b" + re.escape(w) + r"\b", text_klein)]
    if treffer:
        praefix = f"{kontext}: " if kontext else ""
        warn(f"{praefix}Jugendschutz-Stufe ist '{stufe}', aber folgende "
             f"eindeutig explizite Begriffe wurden gefunden: {', '.join(treffer)}")
        warn("Kapitel unbedingt gegenlesen - die Stufe wurde vermutlich "
             "nicht eingehalten.")


_HUNSPELL_VERFUEGBAR = True  # wird beim ersten Fehlschlag auf False gesetzt,
                              # damit nicht bei jedem Kapitel erneut gewarnt wird


def _hunspell_unbekannte_woerter(text: str):
    """Fragt hunspell ab und liefert die Liste unbekannter Woerter
    (dedupliziert, sortiert, Satzzeichen-Reste entfernt). Liefert None, wenn
    hunspell nicht verfuegbar ist oder ein Fehler auftrat - unterscheidet
    sich damit bewusst von einer leeren Liste (= sauber geprueft, nichts
    gefunden)."""
    global _HUNSPELL_VERFUEGBAR
    if not _HUNSPELL_VERFUEGBAR:
        return None

    try:
        ergebnis = subprocess.run(
            ["hunspell", "-d", "de_DE", "-l"],
            input=text, capture_output=True, text=True, timeout=30,
            env={**os.environ, "LC_ALL": "C.UTF-8"},
        )
    except FileNotFoundError:
        _HUNSPELL_VERFUEGBAR = False
        warn("'hunspell' ist nicht installiert. Mit "
             "'apt-get install hunspell hunspell-de-de' nachruesten.")
        return None
    except subprocess.TimeoutExpired:
        warn("hunspell hat zu lange gebraucht (Timeout).")
        return None

    if ergebnis.returncode != 0 and not ergebnis.stdout:
        _HUNSPELL_VERFUEGBAR = False
        warn("hunspell meldet einen Fehler. Ist das Woerterbuch 'de_DE' "
             f"installiert? ({ergebnis.stderr.strip()[:200]})")
        return None

    unbekannt = sorted(set(
        w.strip().strip(".,;:!?…") for w in ergebnis.stdout.splitlines()
    ))
    return [w for w in unbekannt if len(w) > 2]


def _rechtschreibpruefung(text: str, kontext: str = ""):
    """Prueft den Text mit hunspell (deutsches Woerterbuch) auf unbekannte
    Woerter. Ergaenzt die anderen Qualitaets-Checks bewusst um eine andere
    Fehlerart: Ein Sprachmodell prueft, ob ein Wort grammatisch plausibel in
    seine Umgebung passt (Kasus, Genus, Endung), hat aber keine harte
    Woerterbuch-Pruefung. Ein erfundenes, aber grammatisch passendes Wort
    (z.B. "Schmettelving" statt "Schmetterling") faellt einem pruefenden
    Sprachmodell deshalb oft nicht auf - es hat tendenziell dieselben
    blinden Flecken wie das schreibende Modell. hunspell kennt keine
    Bedeutung, aber weiss zuverlaessig, ob ein Wort im Woerterbuch steht.

    Nur ein Hinweis auf der Konsole - fuer die bequeme Durchsicht mit
    sofortiger Korrekturmoeglichkeit siehe './novelle.py rechtschreibung n'.

    WICHTIG entscheidende Einschraenkung: Eigennamen (Figuren, Orte),
    Fachbegriffe und seltene, aber echte Woerter tauchen zwangslaeufig mit
    auf, weil sie im Standard-Woerterbuch fehlen. Das ist kein Fehler des
    Textes - kurz durchsehen und die echten Namen ignorieren."""
    unbekannt = _hunspell_unbekannte_woerter(text)
    if unbekannt:
        praefix = f"{kontext}: " if kontext else ""
        warn(f"{praefix}hunspell kennt folgende Woerter nicht (koennen "
             f"Eigennamen, Fachbegriffe ODER Tippfehler/erfundene Woerter "
             f"sein): {', '.join(unbekannt)}")
        info("Fuer eine bequeme Durchsicht mit direkter Korrektur: "
             "./novelle.py rechtschreibung <n>")


def _satz_mit_wort_finden(text: str, wort: str, max_laenge: int = 220):
    """Findet einen Satz (grob getrennt), der das gegebene Wort als eigenes
    Wort enthaelt - rein zur Anzeige beim interaktiven Rechtschreib-Review.
    Keine exakte Satzgrenzenerkennung noetig, nur genug Kontext zum
    Wiedererkennen."""
    saetze = re.split(r"(?<=[.!?])\s+", text)
    muster = re.compile(r"\b" + re.escape(wort) + r"\b")
    for satz in saetze:
        treffer = muster.search(satz)
        if treffer:
            satz = satz.strip()
            if len(satz) > max_laenge:
                pos = treffer.start()
                start = max(0, pos - max_laenge // 2)
                ende = min(len(satz), pos + max_laenge // 2)
                satz = (("..." if start > 0 else "") + satz[start:ende]
                        + ("..." if ende < len(satz) else ""))
            return satz
    return None


def cmd_rechtschreibung(args):
    """Interaktive Durchsicht der von hunspell gefundenen unbekannten
    Woerter: zeigt Wort und den Satz, in dem es steht. Leere Eingabe
    (Enter) behaelt das Wort, ein eingegebenes Ersatzwort ersetzt es
    ueberall im Kapitel (mit Wortgrenzen, case-sensitiv wie im Original)."""
    if not args:
        fehler("Kapitelnummer fehlt.  Beispiel: ./novelle.py rechtschreibung 3")
    n = int(args[0])
    text = lies(kapitel_datei(n))

    unbekannt = _hunspell_unbekannte_woerter(text)
    if unbekannt is None:
        return  # Warnung kam schon aus _hunspell_unbekannte_woerter
    if not unbekannt:
        ok(f"Kapitel {n}: hunspell hat nichts Unbekanntes gefunden.")
        return

    info(f"Kapitel {n}: {len(unbekannt)} unbekannte(s) Wort/Woerter. "
         f"Enter = behalten, oder Ersatzwort eintippen.")

    geaendert = False
    abgebrochen = False
    for wort in unbekannt:
        satz = _satz_mit_wort_finden(text, wort)
        print("", file=sys.stderr)
        info(f"Wort: '{wort}'")
        if satz:
            print(f"    ...{satz}...", file=sys.stderr)
        else:
            warn("(Wort in keinem klar abgegrenzten Satz gefunden, aber im "
                 "Text vorhanden)")
        try:
            eingabe = input("  Enter=behalten, Ersatzwort=aendern: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            warn("Abgebrochen. Bisherige Aenderungen werden trotzdem gespeichert.")
            abgebrochen = True
            break
        if eingabe:
            muster = re.compile(r"\b" + re.escape(wort) + r"\b")
            anzahl = len(muster.findall(text))
            text = muster.sub(eingabe, text)
            ok(f"  '{wort}' -> '{eingabe}' ({anzahl}x ersetzt)")
            geaendert = True

    print("", file=sys.stderr)
    if geaendert:
        schreib(kapitel_datei(n), text)
        info(f"Kapitel {n} aktualisiert, alte Fassung als .bak gesichert.")
    else:
        info("Keine Aenderungen vorgenommen." + (" (abgebrochen)" if abgebrochen else ""))


def cmd_testen(args):
    """Schreibt dasselbe Kapitel einmal mit der produktiven Autor-Rolle
    (Hermes) und einmal mit der Qwen-Testrolle, speichert beide getrennt zum
    Vergleich. Die eigentliche kapitel_n.md wird NICHT angefasst - reiner
    Vergleichslauf."""
    if not args:
        fehler("Kapitelnummer fehlt.  Beispiel: ./novelle.py testen 3")
    n = int(args[0])

    geruest = lies(PROJEKT / "geruest.md")
    vorher = lies(stand_datei(n - 1), pflicht=False,
                  ersatz="(Kein vorheriger Stand. Dies ist das erste Kapitel.)")
    stufe = _jugendschutz_stufe_erkennen(geruest)
    ziel = _kapitelplan_erkennen(geruest).get(n)
    zielsatz = f"Zielumfang: etwa {ziel} Woerter." if ziel else ""
    aktueller_block = _kapitel_block_erkennen(geruest, n)
    aktueller_hinweis = (
        f"\n\n=== NUR DIESES KAPITEL SCHREIBEN (Kapitel {n}) ===\n{aktueller_block}\n\n"
        f"Bleibe ausschliesslich in der oben fuer DIESES Kapitel beschriebenen "
        f"Stufe der Liebeshandlung. Verwende KEINE Ereignisse, keine "
        f"Explizitheit und keinen Beziehungsstand aus einem ANDEREN Kapitel "
        f"des Gesamtplans."
        if aktueller_block else ""
    )
    auftrag = (
        f"=== STORY-GERUEST ===\n{geruest}\n\n"
        f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
        f"=== AUFTRAG ===\nSchreibe Kapitel {n}. {zielsatz}\n"
        f"Gib ausschliesslich den Kapiteltext aus.\n\n"
        f"{STUFE_DIREKTIVEN[stufe]}"
        f"{aktueller_hinweis}"
    )
    autor_persona = persona("autor")  # dieselbe Persona fuer beide Durchgaenge,
                                        # nur Modell+Parameter unterscheiden sich

    info("=== Durchgang 1 von 2: Hermes (produktive Autor-Rolle) ===")
    start = time.time()
    text_hermes = ollama_chat("autor", autor_persona, auftrag)
    dauer_hermes = time.time() - start

    print("", file=sys.stderr)
    info("=== Durchgang 2 von 2: Qwen (Testrolle) ===")
    start = time.time()
    text_qwen = ollama_chat("autor_qwen_test", autor_persona, auftrag)
    dauer_qwen = time.time() - start

    pfad_hermes = schreib(PROJEKT / f"vergleich_kapitel_{n:02d}_hermes.md",
                           text_hermes, force=True)
    pfad_qwen = schreib(PROJEKT / f"vergleich_kapitel_{n:02d}_qwen.md",
                         text_qwen, force=True)

    print("", file=sys.stderr)
    info("=== Vergleich ===")
    info(f"Hermes: {woerter(text_hermes)} Woerter in {dauer_hermes:.0f}s "
         f"-> {pfad_hermes.name}")
    info(f"Qwen:   {woerter(text_qwen)} Woerter in {dauer_qwen:.0f}s "
         f"-> {pfad_qwen.name}")
    print("", file=sys.stderr)
    info("Automatische Kurzchecks:")
    _pruefe_ausweichformulierungen(text_hermes)
    _sprachdrift_pruefen(text_hermes, kontext="Hermes-Fassung")
    _explizitheit_pruefen(text_hermes, stufe, kontext="Hermes-Fassung")
    _pruefe_ausweichformulierungen(text_qwen)
    _sprachdrift_pruefen(text_qwen, kontext="Qwen-Fassung")
    _explizitheit_pruefen(text_qwen, stufe, kontext="Qwen-Fassung")
    print("", file=sys.stderr)
    info(f"kapitel_{n:02d}.md wurde NICHT veraendert - reiner Vergleichslauf.")


def _stand_sicherstellen(n: int):
    """Prueft vor 'schreiben n', ob der Stand des VORHERIGEN Kapitels
    (stand_(n-1).md) existiert. Fehlt er, wurde vermutlich schlicht
    vergessen, nach dem letzten Kapitel 'stand' aufzurufen - der Chronist
    wird dann automatisch nachgeholt, damit Kapitel n nicht versehentlich
    auf einem veralteten oder fehlenden Stand aufbaut.

    Bei n<=1 ist ein fehlender stand_00.md der korrekte Normalfall (siehe
    Ausgangslage-Mechanismus in cmd_architekt) und wird NICHT nachgeholt -
    da gibt es kein Kapitel 0, aus dem sich ein Stand ableiten liesse.

    Existiert auch das vorherige KAPITEL nicht, ist das ein anderes Problem
    (Kapitel wurden nicht der Reihe nach geschrieben) - das kann hier nicht
    automatisch geheilt werden, nur gemeldet."""
    if n <= 1:
        return
    vorheriger_stand = stand_datei(n - 1)
    if vorheriger_stand.exists():
        return
    vorheriges_kapitel = kapitel_datei(n - 1)
    if not vorheriges_kapitel.exists():
        warn(f"Weder {vorheriger_stand} noch {vorheriges_kapitel} existieren. "
             f"Kapitel {n - 1} scheint nie geschrieben worden zu sein - das "
             f"kann nicht automatisch nachgeholt werden.")
        return
    warn(f"{vorheriger_stand} fehlt, aber {vorheriges_kapitel} existiert - "
         f"vermutlich wurde 'stand {n - 1}' vergessen. Hole das jetzt "
         f"automatisch nach, bevor Kapitel {n} geschrieben wird.")
    cmd_stand([str(n - 1)])


def cmd_schreiben(args):
    if not args:
        fehler("Kapitelnummer fehlt.  Beispiel: ./novelle.py schreiben 3")
    n = int(args[0])
    zusatzhinweis = " ".join(args[1:]).strip()
    _stand_sicherstellen(n)

    geruest = lies(PROJEKT / "geruest.md")
    vorher = lies(stand_datei(n - 1), pflicht=False,
                  ersatz="(Kein vorheriger Stand. Dies ist das erste Kapitel.)")
    stufe = _jugendschutz_stufe_erkennen(geruest)
    autor_rolle = _autor_rolle_erkennen(geruest)
    if autor_rolle != "autor":
        info(f"Autor-Modell laut Geruest: {ROLLEN[autor_rolle]['modell']}")

    ziel = _kapitelplan_erkennen(geruest).get(n)
    zielsatz = f"Zielumfang: etwa {ziel} Woerter." if ziel else ""
    aktueller_block = _kapitel_block_erkennen(geruest, n)
    aktueller_hinweis = (
        f"\n\n=== NUR DIESES KAPITEL SCHREIBEN (Kapitel {n}) ===\n{aktueller_block}\n\n"
        f"Bleibe ausschliesslich in der oben fuer DIESES Kapitel beschriebenen "
        f"Stufe der Liebeshandlung. Verwende KEINE Ereignisse, keine "
        f"Explizitheit und keinen Beziehungsstand aus einem ANDEREN Kapitel "
        f"des Gesamtplans, selbst wenn dort z.B. eine koerperliche Vereinigung "
        f"vorgesehen ist - das gehoert nicht in dieses Kapitel."
        if aktueller_block else ""
    )
    zusatz_block = (
        f"\n\n=== ZUSAETZLICHER HINWEIS FUER DIESEN VERSUCH ===\n{zusatzhinweis}\n"
        f"Dieser Hinweis gilt nur fuer diesen einen Schreibversuch und hat "
        f"Vorrang, falls er einem Detail des Geruests widerspricht."
        if zusatzhinweis else ""
    )
    if zusatzhinweis:
        info(f"Zusaetzlicher Hinweis fuer diesen Versuch: {zusatzhinweis}")

    text = ollama_chat(
        autor_rolle,
        persona("autor"),
        f"=== STORY-GERUEST ===\n{geruest}\n\n"
        f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
        f"=== AUFTRAG ===\n"
        f"Schreibe Kapitel {n}. {zielsatz}\n"
        f"Gib ausschliesslich den Kapiteltext aus.\n\n"
        f"{STUFE_DIREKTIVEN[stufe]}"
        f"{aktueller_hinweis}"
        f"{zusatz_block}",
    )
    text = _kapitel_neustart_abschneiden(text, kontext=f"Kapitel {n}, erster Entwurf")
    text = _vorzeitige_kapitelende_abschneiden(text, kontext=f"Kapitel {n}, erster Entwurf")

    if ziel and _automatische_fortsetzung_aktiviert(geruest):
        text = _bei_bedarf_fortsetzen(n, text, ziel, geruest, vorher, stufe,
                                       zusatzhinweis, autor_rolle)
    elif ziel and woerter(text) < ziel * FORTSETZEN_SCHWELLE:
        info(f"Kapitel {n} liegt bei {woerter(text)} von {ziel} Woertern "
             f"({woerter(text)/ziel:.0%}). Automatische Fortsetzung ist "
             f"(Standard-)deaktiviert - Kapitel bleibt so, wie es ist. Bei "
             f"Bedarf von Hand ergaenzen, per Zusatzhinweis erneut schreiben "
             f"lassen, oder im Geruest 'Automatische Fortsetzung: Ein' setzen.")

    if n == 1:
        titelseite = _titelseite_erzeugen(geruest)
        if titelseite:
            erste_zeile_titelseite = titelseite.strip().split("\n")[0]
            if not text.lstrip().startswith(erste_zeile_titelseite):
                text = titelseite + text
                info("Titelseite (Titel + Untertitel) vorangestellt.")
        else:
            warn("Keine Titelseite erzeugt - '## Titel' wurde im Geruest "
                 "nicht gefunden.")

    schreib(kapitel_datei(n), text)
    if ziel:
        ist = woerter(text)
        abw = (ist - ziel) / ziel * 100
        if abs(abw) > 25:
            warn(f"Umfang weicht deutlich ab: {ist} statt {ziel} Woerter "
                 f"({abw:+.0f} %)")
    _pruefe_ausweichformulierungen(text)
    _sprachdrift_pruefen(text, kontext=f"Kapitel {n} gesamt")
    _explizitheit_pruefen(text, stufe, kontext=f"Kapitel {n}")
    _rechtschreibpruefung(text, kontext=f"Kapitel {n}")
    _erzaehlperspektive_pruefen(text, geruest, kontext=f"Kapitel {n}")
    _anredeform_pruefen(text, kontext=f"Kapitel {n}")

    print("", file=sys.stderr)
    info("Kapitel geschrieben. Jetzt laufen die Pruefer.")
    _pruefe(n, text)

    print("", file=sys.stderr)
    info(f"Naechste Schritte:")
    info(f"  1. {befunde_datei(n)} lesen und entscheiden")
    info(f"  2. {kapitel_datei(n)} von Hand korrigieren")
    info(f"  3. ./novelle.py stand {n}")


# Unter dieser Schwelle (Anteil der Zielwortzahl) wird automatisch
# weitergeschrieben, statt das kurze Kapitel unkommentiert stehen zu lassen.
FORTSETZEN_SCHWELLE = 0.70
FORTSETZEN_MAX_VERSUCHE = 3


# Zeilen, die wie Meta-Kommentare statt Erzaehltext aussehen und aus einer
# Fortsetzung entfernt werden, bevor sie angehaengt wird.
META_ZEILEN_MUSTER = re.compile(
    r"^\s*(-{2,}|#{2,}|\*{2,})\s*$"          # reine Trennstriche/Rauten
    r"|^\s*\[?(wortzahl|word count|gedankenerhebung)\b.*$"
    r"|^\s*\d+\s*w(oe|ö)rter\s*\.?\s*(halte dich .*|halt dich .*|bitte .*)?$"
    r"|^\s*hier ist (die|der|das) (fortgesetzte|fortsetzung|weitere).*$"
    r"|^\s*(fortsetzung|hier folgt die fortsetzung)\s*:?\s*$"
    r"|^\s*kapitel\s+\S+\s+(endet|ist zu ende|ist beendet|ist fertig)\b.*$"
    r"|^\s*(ende|schluss|fortsetzung folgt)\s+(des|von)\s+kapitel\b.*$"
    r"|^\s*dies ist die fortsetzung (des|von) kapitel.*$",
    re.IGNORECASE,
)


def _meta_zeilen_entfernen(text: str) -> str:
    zeilen = [z for z in text.split("\n") if not META_ZEILEN_MUSTER.match(z)]
    return "\n".join(zeilen).strip()


_KAPITEL_UEBERSCHRIFT_MUSTER = re.compile(r"^\s*Kapitel\s+\S+\s*:", re.IGNORECASE | re.MULTILINE)


def _kapitel_neustart_abschneiden(text: str, kontext: str = "") -> str:
    """Erkennt, ob die Kapitelueberschrift ein zweites Mal im Text auftaucht,
    und schneidet in diesem Fall alles ab der zweiten Ueberschrift ab.

    Hintergrund: Wird ein Kapitel automatisch fortgesetzt (siehe
    _bei_bedarf_fortsetzen), kommt es vor, dass das Modell trotz expliziter
    Anweisung ("nicht wiederholen, nicht neu beginnen") keinen echten
    Anschluss schreibt, sondern einen komplett NEUEN, oft inhaltlich
    widersprechenden zweiten Durchlauf des ganzen Kapitels - inklusive
    eigener, wiederholter Ueberschrift. Der bestehende Duplikat-Filter
    (_fuehrende_duplikate_entfernen) erkennt das nicht, weil er nur
    wortwoertliche Wiederholungen abgleicht - eine neu formulierte, andere
    zweite Fassung faellt da durch.

    Eine zweite Kapitelueberschrift im selben Kapiteltext kommt in einer
    echten, korrekten Fortsetzung nie vor - das macht sie zu einem
    zuverlaessigen, rein mechanischen Stopp-Signal."""
    treffer = list(_KAPITEL_UEBERSCHRIFT_MUSTER.finditer(text))
    if len(treffer) <= 1:
        return text
    grenze = treffer[1].start()
    praefix = f"{kontext}: " if kontext else ""
    warn(f"{praefix}Die Kapitelueberschrift wurde ein zweites Mal gefunden - "
         f"das Modell hat vermutlich neu angefangen statt fortzusetzen. "
         f"Text ab der zweiten Ueberschrift automatisch abgeschnitten.")
    return text[:grenze].rstrip()


_KAPITEL_ENDE_ERKLAERUNG_MUSTER = re.compile(
    r"(das kapitel (endete|endet|ist zu ende|erreichte seinen abschluss)|"
    r"und damit (endete|hatte) (das )?kapitel)",
    re.IGNORECASE,
)


def _vorzeitige_kapitelende_abschneiden(text: str, kontext: str = "",
                                          mindest_rest: int = 50) -> str:
    """Erkennt, wenn der Text mitten drin eine Selbstaussage macht, dass das
    Kapitel jetzt beendet sei (z.B. "Das Kapitel endete damit, dass..."),
    aber DANACH trotzdem noch substanziell weitergeht - meist mit einer
    voellig neuen, ungeplanten Szene ("Zwei Tage spaeter...").

    Hintergrund: eine dritte Ausprägung desselben Grundproblems wie
    _kapitel_neustart_abschneiden (doppelte Ueberschrift) und die erweiterte
    META_ZEILEN_MUSTER-Erkennung (Wortzahl-Selbstkommentare) - die
    automatische Fortsetzung setzt die laufende Szene nicht fort, sondern
    beginnt eine neue. Hier ist der Marker aber keine eigene Zeile, sondern
    in einen normalen Erzaehlsatz eingebettet, deshalb per Volltextsuche
    statt zeilenweisem Abgleich wie beim Meta-Zeilen-Filter.

    Kommt nach der Erklaerung nur noch wenig Text (< mindest_rest Woerter,
    z.B. ein runder Schlusssatz), wird nichts abgeschnitten - das waere
    vermutlich ein legitimer, beabsichtigter Kapitelschluss."""
    treffer = _KAPITEL_ENDE_ERKLAERUNG_MUSTER.search(text)
    if not treffer:
        return text
    satzende = text.find(".", treffer.end())
    grenze = satzende + 1 if satzende != -1 else treffer.end()
    rest = text[grenze:].strip()
    if woerter(rest) < mindest_rest:
        return text
    praefix = f"{kontext}: " if kontext else ""
    warn(f"{praefix}Der Text erklaert sich mitten drin selbst fuer beendet "
         f"(Fundstelle: '{treffer.group(0)}'), schreibt danach aber noch "
         f"{woerter(rest)} Woerter weiter - vermutlich eine ungeplante neue "
         f"Szene nach einer Fortsetzung. Text ab dieser Stelle automatisch "
         f"abgeschnitten.")
    return text[:grenze].rstrip()


def _fuehrende_duplikate_entfernen(bisheriger_text: str, fortsetzung: str,
                                    max_fenster: int = 4) -> str:
    """Manche Modelle wiederholen trotz gegenteiliger Anweisung den letzten
    Absatz oder mehrere, bevor sie tatsaechlich neuen Text liefern. Diese
    Funktion prueft, ob die ERSTEN k Absaetze der Fortsetzung mit den LETZTEN
    k Absaetzen des bisherigen Texts uebereinstimmen (in derselben
    Reihenfolge), fuer absteigende Fenstergroessen, und entfernt den groessten
    gefundenen Treffer."""
    bisherige = [a for a in bisheriger_text.split("\n\n") if a.strip()]
    neue = [a for a in fortsetzung.split("\n\n") if a.strip()]

    fenster_max = min(max_fenster, len(bisherige), len(neue))
    for k in range(fenster_max, 0, -1):
        alte_fenster = bisherige[-k:]
        neue_fenster = neue[:k]
        aehnlichkeiten = [
            difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio()
            for a, b in zip(alte_fenster, neue_fenster)
        ]
        if min(aehnlichkeiten) > 0.75:
            warn(f"{k} wiederholte(r) Absatz/Absaetze aus der Fortsetzung "
                 f"entfernt (Modell hat trotz Anweisung dupliziert).")
            return "\n\n".join(neue[k:])

    return fortsetzung


def _bei_bedarf_fortsetzen(n, text, ziel, geruest, vorher, stufe="voll",
                            zusatzhinweis="", autor_rolle="autor"):
    """Laesst den Autor nahtlos weiterschreiben, wenn ein Kapitel deutlich
    zu kurz ausfaellt. Kleine Modelle brechen Szenen manchmal frueh ab, statt
    sie im geforderten Umfang auszuspielen; ein zweiter Aufruf mit dem
    bisherigen Text als Grundlage behebt das meist zuverlaessiger als ein
    kompletter Neuversuch."""
    versuch = 0
    aktueller_block = _kapitel_block_erkennen(geruest, n)
    aktueller_hinweis = (
        f"\n\n=== NUR DIESES KAPITEL FORTSETZEN (Kapitel {n}) ===\n{aktueller_block}\n\n"
        f"Bleibe ausschliesslich in der oben fuer DIESES Kapitel beschriebenen "
        f"Stufe der Liebeshandlung. Erfinde KEINE neue Szene und springe zu "
        f"KEINEM anderen Beziehungsstand (z.B. Heirat, koerperliche Vereinigung "
        f"oder ein gemeinsames Erwachen als Paar), auch wenn ein spaeteres "
        f"Kapitel im Gesamtplan das vorsieht - das gehoert nicht hierher. "
        f"Fuehre exakt die laufende Szene fort."
        if aktueller_block else ""
    )
    zusatz_block = (
        f"\n\n=== ZUSAETZLICHER HINWEIS FUER DIESEN VERSUCH ===\n{zusatzhinweis}\n"
        f"Dieser Hinweis gilt nur fuer diesen einen Schreibversuch und hat "
        f"Vorrang, falls er einem Detail des Geruests widerspricht."
        if zusatzhinweis else ""
    )

    while woerter(text) < ziel * FORTSETZEN_SCHWELLE and versuch < FORTSETZEN_MAX_VERSUCHE:
        versuch += 1
        fehlend = ziel - woerter(text)
        warn(f"Kapitel {n} liegt bei {woerter(text)} von {ziel} Woertern "
             f"({woerter(text)/ziel:.0%}). Lasse automatisch fortsetzen "
             f"(Versuch {versuch}/{FORTSETZEN_MAX_VERSUCHE}).")

        # Nur das Ende als Anschlusspunkt mitgeben, nicht den ganzen Text
        # erneut - spart Kontext und verhindert, dass der Autor von vorn
        # beginnt.
        anschluss = text[-600:]

        fortsetzung = ollama_chat(
            autor_rolle,
            persona("autor"),
            f"=== STORY-GERUEST ===\n{geruest}\n\n"
            f"=== STAND NACH DEM VORIGEN KAPITEL ===\n{vorher}\n\n"
            f"=== BISHERIGER TEXT DIESES KAPITELS (Ende) ===\n...{anschluss}\n\n"
            f"=== AUFTRAG ===\n"
            f"Der obige Text ist noch nicht zu Ende. Schreibe NAHTLOS weiter, "
            f"genau ab der letzten Zeile, ohne sie zu wiederholen und ohne "
            f"neu zu beginnen. Fuehre die Szene tatsaechlich aus, statt sie "
            f"nur anzudeuten oder abzukuerzen. Noch etwa {fehlend} Woerter, "
            f"bis das Kapitel gemaess Geruest inhaltlich abgeschlossen ist. "
            f"Gib ausschliesslich die Fortsetzung aus, keine Wiederholung "
            f"des bisherigen Textes. Schreibe ausschliesslich auf Deutsch, "
            f"auch wenn im bisherigen Text ein anderer Sprachanteil "
            f"vorkommen sollte.\n\n"
            f"{STUFE_DIREKTIVEN[stufe]}"
            f"{aktueller_hinweis}"
            f"{zusatz_block}",
        )
        fortsetzung = _meta_zeilen_entfernen(fortsetzung)
        fortsetzung = _fuehrende_duplikate_entfernen(text, fortsetzung)
        _sprachdrift_pruefen(fortsetzung, kontext=f"Fortsetzung {versuch} von Kapitel {n}")
        _erzaehlperspektive_pruefen(fortsetzung, geruest,
                                     kontext=f"Fortsetzung {versuch} von Kapitel {n}")
        text = text.rstrip() + "\n\n" + fortsetzung.strip()
        text = _kapitel_neustart_abschneiden(
            text, kontext=f"Kapitel {n}, nach Fortsetzung {versuch}")
        text = _vorzeitige_kapitelende_abschneiden(
            text, kontext=f"Kapitel {n}, nach Fortsetzung {versuch}")

    if woerter(text) < ziel * FORTSETZEN_SCHWELLE:
        warn(f"Auch nach {versuch} Fortsetzungsversuchen bleibt Kapitel {n} "
             f"kurz ({woerter(text)} von {ziel} Woertern). Persona oder "
             f"Gerueststruktur pruefen, statt weiter automatisch zu versuchen.")

    return text


def cmd_pruefen(args):
    if not args:
        fehler("Kapitelnummer fehlt.  Beispiel: ./novelle.py pruefen 3")
    n = int(args[0])
    _pruefe(n, lies(kapitel_datei(n)))


def _aenderungen_anzeigen(alt: str, neu: str, max_zeilen: int = 14):
    """Kompakte Aenderungsuebersicht per Zeilen-Diff. Kein Ersatz fuer
    manuelles Gegenlesen, aber genug Transparenz, um zu sehen, was der
    Lektor tatsaechlich veraendert hat, ohne selbst diffen zu muessen."""
    diff = list(difflib.unified_diff(
        alt.splitlines(), neu.splitlines(), lineterm="", n=0))
    aenderungszeilen = [z for z in diff
                         if z.startswith(("+", "-"))
                         and not z.startswith(("+++", "---"))]
    if not aenderungszeilen:
        info("Lektor hat keine Aenderungen vorgenommen.")
        return
    info(f"Lektor hat {len(aenderungszeilen)} Zeile(n) veraendert:")
    for zeile in aenderungszeilen[:max_zeilen]:
        praefix = f"{F.ROT}-{F.AUS}" if zeile.startswith("-") else f"{F.GRUEN}+{F.AUS}"
        print(f"    {praefix} {zeile[1:].strip()}", file=sys.stderr)
    rest = len(aenderungszeilen) - max_zeilen
    if rest > 0:
        info(f"... und {rest} weitere veraenderte Zeile(n).")


def cmd_anwenden(args):
    """Wendet NUR die Anachronismus-Befunde mit Sicherheit 'hoch' UND einem
    konkreten Ersatzvorschlag automatisch an. Funde mit 'mittel'/'gering' oder
    ohne konkreten Vorschlag bleiben unangetastet - die stehen weiterhin in
    der Befunde-Datei zur manuellen Entscheidung."""
    if not args:
        fehler("Kapitelnummer fehlt.  Beispiel: ./novelle.py anwenden 3")
    n = int(args[0])

    text_alt = lies(kapitel_datei(n))
    befunde = lies(befunde_datei(n), pflicht=True)

    text_neu = ollama_chat(
        "anachronismen_korrektur",
        persona("anachronismen_korrektur"),
        f"=== BEFUNDE (nur der Abschnitt Anachronismen ist relevant) ===\n"
        f"{befunde}\n\n"
        f"=== KAPITELTEXT ===\n{text_alt}",
    )

    if woerter(text_neu) < woerter(text_alt) * 0.7:
        warn(f"Korrigierte Fassung ist deutlich kuerzer als das Original "
             f"({woerter(text_neu)} statt {woerter(text_alt)} Woerter). "
             f"Nicht automatisch uebernommen - bitte pruefen:")
        print(text_neu, file=sys.stderr)
        return

    _aenderungen_anzeigen(text_alt, text_neu)
    schreib(kapitel_datei(n), text_neu)  # sichert die alte Fassung automatisch
    info(f"Kapitel {n}: hochsichere Anachronismus-Funde mit konkretem "
         f"Vorschlag wurden angewendet. Alte Fassung als .bak gesichert.")
    warn(f"Funde mit Sicherheit 'mittel'/'gering' oder ohne konkreten "
         f"Vorschlag wurden NICHT automatisch geaendert. Bitte "
         f"{befunde_datei(n)} weiterhin von Hand durchsehen.")


def cmd_lektorieren(args):
    if not args:
        fehler("Kapitelnummer fehlt.  Beispiel: ./novelle.py lektorieren 3")
    n = int(args[0])

    text_alt = lies(kapitel_datei(n))
    geruest = lies(PROJEKT / "geruest.md", pflicht=False,
                   ersatz="(kein Geruest gefunden)")

    text_neu = ollama_chat(
        "lektor",
        persona("lektor"),
        f"=== STORY-GERUEST (fuer Namen, Staende, Tonlage) ===\n{geruest}\n\n"
        f"=== KAPITELTEXT ===\n{text_alt}",
    )

    if woerter(text_neu) < woerter(text_alt) * 0.7:
        warn(f"Lektorierte Fassung ist deutlich kuerzer als das Original "
             f"({woerter(text_neu)} statt {woerter(text_alt)} Woerter). "
             f"Nicht automatisch uebernommen - bitte pruefen:")
        print(text_neu, file=sys.stderr)
        return

    _aenderungen_anzeigen(text_alt, text_neu)
    schreib(kapitel_datei(n), text_neu)  # sichert die alte Fassung automatisch
    info(f"Kapitel {n} lektoriert. Alte Fassung liegt als .bak daneben.")
    _rechtschreibpruefung(text_neu, kontext=f"Kapitel {n} (lektoriert)")


def cmd_stand(args):
    if not args:
        fehler("Kapitelnummer fehlt.  Beispiel: ./novelle.py stand 3")
    n = int(args[0])

    kapiteltext = lies(kapitel_datei(n))
    vorher = lies(stand_datei(n - 1), pflicht=False,
                  ersatz="(Kein vorheriger Stand vorhanden.)")

    warn("Der Chronist sollte erst nach der Korrektur laufen. "
         "Ist Kapitel {} final?".format(n))

    text = ollama_chat(
        "chronist",
        persona("chronist"),
        f"=== BISHERIGER STAND ===\n{vorher}\n\n"
        f"=== KAPITEL {n} ===\n{kapiteltext}\n\n"
        f"=== AUFTRAG ===\nAktualisiere den Stand auf Kapitel {n}.",
    )
    schreib(stand_datei(n), text)

    # Automatisches Zusammenfuegen, sobald das letzte laut Geruest geplante
    # Kapitel erreicht ist. Die einzelnen kapitel_NN.md-Dateien bleiben dabei
    # unangetastet, cmd_export liest sie nur.
    geplant = _kapitelplan_erkennen(lies(PROJEKT / "geruest.md", pflicht=False, ersatz=""))
    letztes_geplantes_kapitel = max(geplant.keys()) if geplant else None
    vorhandene_kapitel = sorted(PROJEKT.glob("kapitel_*.md"))

    if letztes_geplantes_kapitel and n == letztes_geplantes_kapitel \
            and len(vorhandene_kapitel) >= letztes_geplantes_kapitel:
        print("", file=sys.stderr)
        info(f"Kapitel {n} ist laut Geruest das letzte geplante Kapitel. "
             f"Fuege alle Kapitel automatisch zu projekt/gesamt.md zusammen.")
        cmd_export([])
        info("Die einzelnen kapitel_NN.md-Dateien bleiben unveraendert erhalten.")
    elif letztes_geplantes_kapitel is None:
        # Kapitelplan konnte nicht zuverlaessig ausgelesen werden - keine
        # automatische Zusammenfuehrung, aber auch keine falsche Warnung.
        pass


def cmd_gesamt(_args):
    """Endkontrolle ueber den kompletten Text."""
    kapitel = sorted(PROJEKT.glob("kapitel_*.md"))
    if not kapitel:
        fehler("Keine Kapitel gefunden.")

    ganz = "\n\n".join(p.read_text(encoding="utf-8").strip() for p in kapitel)
    info(f"{len(kapitel)} Kapitel, {woerter(ganz)} Woerter gesamt.")

    geruest = lies(PROJEKT / "geruest.md")
    verbote = lies(PROJEKT / "verbotsliste.md")
    jahr = "unbekannt"
    treffer = re.search(r"\b(1[0-9]{3})\b", geruest)
    if treffer:
        jahr = treffer.group(1)

    gross = {"num_ctx": GESAMT_NUM_CTX, "num_predict": GESAMT_NUM_PREDICT}

    a = ollama_chat(
        "anachronismus", persona("pruefer_anachronismus"),
        f"JAHR: {jahr}\n\n=== VERBOTSLISTE ===\n{verbote}\n\n"
        f"=== GESAMTTEXT ===\n{ganz}",
        ueberschreibe=gross,
    )
    k = ollama_chat(
        "kontinuitaet", persona("pruefer_kontinuitaet"),
        "Dies ist der vollstaendige Text. Achte besonders auf Widersprueche "
        "ueber groessere Abstaende hinweg und auf angedeutete Faeden, "
        "die nie eingeloest wurden.\n\n"
        f"=== STORY-GERUEST ===\n{geruest}\n\n=== GESAMTTEXT ===\n{ganz}",
        ueberschreibe=gross,
    )

    schreib(PROJEKT / "befunde_gesamt.md",
            f"# Endkontrolle ueber den Gesamttext\n\n"
            f"Erzeugt: {time.strftime('%Y-%m-%d %H:%M')}\n"
            f"{len(kapitel)} Kapitel, {woerter(ganz)} Woerter\n\n"
            f"---\n\n## Anachronismen\n\n{a}\n\n"
            f"---\n\n## Kontinuitaet und Logik\n\n{k}\n")


def _titelseite_erzeugen(geruest: str) -> str:
    """Baut eine Titelseite (Titel + Untertitel) aus dem Geruest, fuer den
    Export vorangestellt. Titel kommt aus dem '## Titel'-Abschnitt, das Jahr
    aus derselben Erkennung wie fuer die Pruefer, die Epoche (falls bekannt)
    aus der bei Projekterstellung hinterlegten Marker-Datei. Fehlt eine
    dieser Angaben, wird die Titelseite trotzdem erzeugt, nur ohne die
    fehlende Information - lieber unvollstaendig als gar keine Titelseite."""
    titel_treffer = re.search(r"##\s*Titel\s*\n+(.+)", geruest)
    titel = titel_treffer.group(1).strip() if titel_treffer else None

    jahr_treffer = re.search(r"Jahr\s*[:\-]?\s*(\d{1,5})", geruest, re.IGNORECASE)
    if not jahr_treffer:
        jahr_treffer = re.search(r"\b([12][0-9]{3})\b", geruest)
    jahr = jahr_treffer.group(1) if jahr_treffer else None

    epoche_marker = PROJEKT / ".epoche"
    epoche = epoche_marker.read_text(encoding="utf-8").strip() if epoche_marker.exists() else None

    if not titel:
        return ""  # Ohne Titel keine sinnvolle Titelseite - lieber weglassen

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


def cmd_export(_args):
    kapitel = sorted(PROJEKT.glob("kapitel_*.md"))
    if not kapitel:
        fehler("Keine Kapitel gefunden.")
    # Die Titelseite steckt inzwischen bereits in kapitel_01.md selbst (siehe
    # cmd_schreiben) - hier nur noch reines Zusammenfuegen, sonst wuerde die
    # Titelseite doppelt auftauchen.
    ganz = "\n\n\n".join(p.read_text(encoding="utf-8").strip() for p in kapitel)
    ziel = schreib(PROJEKT / "gesamt.md", ganz, force=True)
    info(f"{len(kapitel)} Kapitel zusammengefuegt: {ziel}")


def _kapitelnummer_aus_dateiname(pfad: Path) -> int:
    treffer = re.search(r"kapitel_(\d+)\.md$", pfad.name)
    return int(treffer.group(1)) if treffer else -1


def cmd_zusammenfassen(args):
    """Fasst Kapitel manuell zu einer Datei zusammen - jederzeit aufrufbar,
    nicht nur automatisch am Schluss (siehe 5.9/cmd_stand). Zwei Modi:
    ohne Argumente alle vorhandenen Kapitel (identisch zu 'export'), mit
    zwei Zahlen nur der angegebene Bereich - nuetzlich fuer Zwischenstaende
    waehrend des Schreibens, ohne die Geschichte als fertig zu markieren."""
    if not args:
        cmd_export([])
        return

    if len(args) != 2:
        fehler("Entweder keine Angabe (alle Kapitel) oder genau zwei Zahlen "
               "fuer den Bereich.  Beispiel: ./novelle.py zusammenfassen 1 3")
    von, bis = int(args[0]), int(args[1])
    if von > bis:
        von, bis = bis, von

    alle_kapitel = sorted(PROJEKT.glob("kapitel_*.md"),
                           key=_kapitelnummer_aus_dateiname)
    ausgewaehlt = [p for p in alle_kapitel
                   if von <= _kapitelnummer_aus_dateiname(p) <= bis]
    if not ausgewaehlt:
        fehler(f"Keine Kapitel im Bereich {von}-{bis} gefunden.")

    vorhandene_nummern = {_kapitelnummer_aus_dateiname(p) for p in ausgewaehlt}
    fehlende = [n for n in range(von, bis + 1) if n not in vorhandene_nummern]
    if fehlende:
        warn(f"Kapitel {', '.join(str(n) for n in fehlende)} im Bereich "
             f"{von}-{bis} fehlen und werden ausgelassen.")

    ganz = "\n\n\n".join(p.read_text(encoding="utf-8").strip() for p in ausgewaehlt)
    ziel_name = f"zusammen_{von:02d}-{bis:02d}.md"
    ziel = schreib(PROJEKT / ziel_name, ganz, force=True)
    info(f"{len(ausgewaehlt)} Kapitel (Bereich {von}-{bis}) zusammengefuegt: {ziel}")


def cmd_modelle(_args):
    geladen = ollama_get("/api/ps").get("models", [])
    alle = ollama_get("/api/tags").get("models", [])

    print("\nGeladen:", file=sys.stderr)
    if geladen:
        for m in geladen:
            gb = m.get("size", 0) / 1e9
            print(f"  {m['name']:28} {gb:5.1f} GB", file=sys.stderr)
    else:
        print("  (keines)", file=sys.stderr)

    print("\nVerfuegbar:", file=sys.stderr)
    namen = set()
    for m in alle:
        gb = m.get("size", 0) / 1e9
        namen.add(m["name"].split(":")[0])
        namen.add(m["name"])
        print(f"  {m['name']:28} {gb:5.1f} GB", file=sys.stderr)

    print("\nIn den Rollen eingetragen:", file=sys.stderr)
    for rolle, cfg in ROLLEN.items():
        da = "ok " if cfg["modell"] in namen else "FEHLT"
        print(f"  {rolle:16} {cfg['modell']:20} {da}", file=sys.stderr)
    print("", file=sys.stderr)


def _epoche_waehlen():
    """Listet die Unterordner von epochen/ auf und laesst den Nutzer waehlen.
    Reine Python-Logik, absichtlich OHNE LLM-Aufruf - eine Ordnerliste
    einzulesen ist zuverlaessige Handarbeit, kein Fall fuer ein 8B-Modell,
    das dabei Epochen erfinden oder falsch benennen koennte."""
    if not EPOCHEN_ORDNER.exists():
        fehler(f"Epochen-Ordner nicht gefunden: {EPOCHEN_ORDNER}\n"
               f"       Liegt neben dem Skript ein Ordner 'epochen/' mit "
               f"je einem Unterordner pro Setting?")
    optionen = sorted(p.name for p in EPOCHEN_ORDNER.iterdir() if p.is_dir())
    if not optionen:
        fehler(f"Keine Epochen-Unterordner gefunden in {EPOCHEN_ORDNER}")

    if len(optionen) == 1:
        info(f"Nur eine Epoche vorhanden, verwende automatisch: {optionen[0]}")
        return optionen[0]

    print("", file=sys.stderr)
    info("Welche Epoche/welches Setting soll verwendet werden?")
    for i, name in enumerate(optionen, 1):
        print(f"    {i}) {name}", file=sys.stderr)
    while True:
        try:
            wahl = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            fehler("Abgebrochen.")
        if wahl.isdigit() and 1 <= int(wahl) <= len(optionen):
            return optionen[int(wahl) - 1]
        warn(f"Ungueltige Auswahl. Bitte eine Zahl von 1 bis {len(optionen)} eingeben.")


def _projekt_befuellen(ziel: Path, epoche: str):
    """Legt personas/ und projekt/ in ziel an: die vier epochenlosen Rollen
    aus der zentralen Bibliothek, die drei epochenspezifischen Rollen plus
    Verbotsliste aus epochen/<epoche>/, dazu die generischen Leer-Vorlagen."""
    personas_ziel = ziel / "personas"
    projekt_ziel = ziel / "projekt"
    personas_ziel.mkdir(parents=True, exist_ok=True)
    projekt_ziel.mkdir(parents=True, exist_ok=True)
    epoche_ordner = EPOCHEN_ORDNER / epoche

    def _kopieren(quelle: Path, ziel_datei: Path):
        if not quelle.exists():
            fehler(f"Vorlage fehlt: {quelle}")
        if ziel_datei.exists():
            warn(f"vorhanden, uebersprungen: {ziel_datei}")
        else:
            ziel_datei.write_bytes(quelle.read_bytes())
            ok(f"angelegt: {ziel_datei}")

    for datei in GEMEINSAME_PERSONA_DATEIEN:
        _kopieren(GEMEINSAME_PERSONAS_ORDNER / datei, personas_ziel / datei)

    for datei in EPOCHE_PERSONA_DATEIEN:
        _kopieren(epoche_ordner / datei, personas_ziel / datei)

    _kopieren(epoche_ordner / "verbotsliste.md", projekt_ziel / "verbotsliste.md")

    for name, inhalt in (("geruest.md", GERUEST_VORLAGE),):
        p = projekt_ziel / name
        if p.exists():
            warn(f"vorhanden, uebersprungen: {p}")
        else:
            p.write_text(inhalt.strip() + "\n", encoding="utf-8")
            ok(f"angelegt: {p}")

    # Epoche merken, damit spaetere Schritte (z.B. die Titelseite bei
    # 'export') wissen, aus welchem Setting die Geschichte stammt, ohne dass
    # das im Geruest selbst wiederholt werden muss.
    epoche_marker = projekt_ziel / ".epoche"
    if not epoche_marker.exists():
        epoche_marker.write_text(epoche + "\n", encoding="utf-8")


def cmd_init(_args):
    epoche = _epoche_waehlen()
    _projekt_befuellen(Path("."), epoche)

    print("", file=sys.stderr)
    info(f"Projekt im aktuellen Ordner eingerichtet (Epoche: {epoche}).")
    info("Naechste Schritte:")
    info("  1. ./novelle.py modelle          Modellnamen pruefen")
    info("  2. ./novelle.py architekt        Geruest erarbeiten")
    info("  3. ./novelle.py schreiben 1")


def _ordnername_aus_titel(titel: str) -> str:
    """Macht aus einem frei geschriebenen Titel ('Der Markt von Rothenfeld')
    einen dateisystem-tauglichen Ordnernamen ('Der-Markt-von-Rothenfeld').
    Umlaute werden transliteriert statt entfernt, damit der Name noch lesbar
    bleibt; alles andere, was in Pfaden Aerger machen kann, fliegt raus."""
    ersatz = {"ä": "ae", "ö": "oe", "ü": "ue",
              "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
    for a, b in ersatz.items():
        titel = titel.replace(a, b)
    titel = re.sub(r"\s+", "-", titel.strip())
    titel = re.sub(r"[^A-Za-z0-9\-_.]", "", titel)
    titel = re.sub(r"-{2,}", "-", titel).strip("-")
    return titel or "Neues-Projekt"


def cmd_neu(args):
    """Legt einen neuen, eigenstaendigen Projektordner an: personas/ und
    projekt/ werden aus der zentralen Bibliothek (epochen/ + gemeinsame
    Personas) befuellt, das Skript selbst wird nur VERKNUEPFT, nicht
    kopiert - es gibt nur eine echte novelle.py, egal wie viele
    Projektordner existieren. Das laufende Projekt im aktuellen Ordner
    bleibt unangetastet."""
    if not args:
        fehler("Titel oder Name fehlt.  "
               "Beispiel: ./novelle.py neu Der Markt von Rothenfeld")
    titel = " ".join(args)
    ziel = Path(_ordnername_aus_titel(titel))

    if ziel.exists() and any(ziel.iterdir()):
        fehler(f"Ordner '{ziel}' existiert bereits und ist nicht leer. "
               f"Anderen Titel waehlen oder Ordner erst entfernen.")
    ziel.mkdir(parents=True, exist_ok=True)

    epoche = _epoche_waehlen()
    _projekt_befuellen(ziel, epoche)

    # Symlink statt Kopie: nur EIN echtes Skript soll existieren, damit
    # Bugfixes kuenftig nicht mehr in jeden Projektordner einzeln kopiert
    # werden muessen.
    ziel_skript = ziel / EIGENE_DATEI.name
    try:
        ziel_skript.symlink_to(EIGENE_DATEI)
        ok(f"Verknuepfung angelegt: {ziel_skript} -> {EIGENE_DATEI}")
    except OSError as e:
        # Falls Symlinks auf dem jeweiligen Dateisystem nicht moeglich sind:
        # ersatzweise kopieren, aber deutlich darauf hinweisen.
        ziel_skript.write_bytes(EIGENE_DATEI.read_bytes())
        ziel_skript.chmod(EIGENE_DATEI.stat().st_mode)
        warn(f"Symlink nicht moeglich ({e}), Skript stattdessen kopiert. "
             f"Kuenftige Bugfixes muessten dann erneut hierher kopiert werden.")

    if str(ziel) != titel:
        info(f"Titel '{titel}' -> Ordnername '{ziel}'")

    print("", file=sys.stderr)
    info(f"Neues Projekt angelegt: {ziel}/  (Epoche: {epoche})")
    info("Naechste Schritte:")
    info(f"  1. cd {ziel}")
    info(f"  2. ./novelle.py modelle          Modellnamen pruefen")
    info(f"  3. ./novelle.py architekt")


GERUEST_VORLAGE = """
# STORY-GERUEST

Diese Datei wird vom Architekten erzeugt.
Rufe dazu auf:  ./novelle.py architekt
und kopiere das Ergebnis hierher.

Wichtig: Die Jahres- oder Zeitangabe muss eindeutig im Text stehen, direkt
mit dem Wort "Jahr" davor (z.B. "Jahr: 1815" oder "Jahr 214 der eigenen
Zeitrechnung"). Das Skript liest sie automatisch aus und gibt sie an die
Pruefer weiter.

## Rahmen
(noch nicht ausgefuellt)

## Kapitelplan
(noch leer)
"""


# ---------------------------------------------------------------------------
# Epochen-Ersteller: reines Frageformular (kein LLM), erzeugt einen Rohentwurf
# fuer eine neue Epoche unter epochen/<name>/.
#
# WICHTIG, ehrlich gesagt: Dieser Assistent liefert ein solides Skelett mit
# der immer gleichen, bewaehrten Struktur (Interviewmechanik, Phasenaufbau
# fuer Vereinigungsszenen, Formatregeln - das alles wortgleich uebernommen).
# Was er NICHT zuverlaessig liefern kann, ist die inhaltliche Tiefe der
# Verbotsliste und die feinen Nuancen der Gesellschaftsordnung - das ist
# Recherchearbeit, die besser von Hand oder in einem Gespraech mit einem
# staerkeren Sprachmodell passiert. Der Rohentwurf markiert solche Stellen
# ausdruecklich mit "HIER ERGAENZEN".
# ---------------------------------------------------------------------------

_ARCHITEKT_INTERVIEW_BLOCK = '''## WICHTIGSTE REGEL - IMMER ZUERST BEFOLGEN
Du fuehrst ein Interview. Stelle GENAU EINE Frage, warte auf Antwort, dann die
naechste. NIEMALS selbst antworten. NIEMALS mehrere Fragen auf einmal. NIEMALS eine
Frage ueberspringen. Nach der Frage schreibst du NICHTS weiter: kein Kommentar,
keine Zusammenfassung, keine Ideen, keine Handlung.
Das gilt auch dann, wenn Daniel nur "lass uns eine Geschichte schreiben" schreibt.

FALSCH (mehrere Fragen zusammengefasst, auch wenn sie nummeriert und mit
Fettdruck-Ueberschrift ordentlich aussehen):
"1. **Setting:** Epoche, Jahr, Ort, Jahreszeit?
2. **Hauptfiguren:** Name, Alter, Stand...?
3. **Nebenfiguren:** Wie viele und welche Funktion?"

RICHTIG (nur die eine, aktuell faellige Frage, sonst nichts):
"Frage 2 von 10: In welchem Ort und in welcher Jahreszeit soll die Geschichte
spielen?
a) ...
b) ...
c) ...
d) Eigene Angabe"

Jede Frage im Multiple-Choice-Format a/b/c/d, wobei die letzte Option immer das
freie Selbstformulieren erlaubt.

Deine ERSTE Antwort in einem neuen Gespraech muss EXAKT so aussehen, kein Wort mehr,
kein Wort weniger:

"Frage 1 von 10: Wie lang soll die Geschichte ungefaehr sein?
a) Kurz (~2.500 Woerter, 2 Kapitel)
b) Mittel (~5.000 Woerter, 4 Kapitel)
c) Erzaehlung (~9.500 Woerter, 6 Kapitel)
d) Eigene Wort- und Kapitelzahl angeben"

Danach: STOPP. Kein weiterer Text.'''

_AUTOR_PHASEN_BLOCK = '''### Pflicht bei Kapiteln mit koerperlicher Vereinigung
Eine Nacht der Vereinigung wird NIEMALS als kurze Montage oder Zusammenfassung
erzaehlt. Du zerlegst die Szene zwingend in einzelne, nacheinander ausgefuehrte
Phasen, jede davon mit konkreter Handlung, nicht mit einem Satz uebersprungen:
1. Anziehung und erste Beruehrung
2. Entkleiden
3. Vorspiel: Kuesse, Haende, ausdruecklich auch Mund auf Koerper (Oralsex),
   Fingerspiel, je nach Kapitelkontext
4. Der eigentliche Akt: konkrete koerperliche Handlung, Positionen, Bewegung,
   koerperliche Reaktionen beider Figuren
5. Hoehepunkt beider Figuren, konkret beschrieben
6. Nachspiel: koerperliche und emotionale Reaktion, Naehe, Gespraech oder Stille

Jede dieser Phasen bekommt eigenen Raum im Text. Das Kapitel darf NICHT von
Phase 1 direkt zu einer zusammenfassenden Ueberleitung springen. Wird eine Phase
uebersprungen oder nur angedeutet, ist das Kapitel unvollstaendig.

### Verbotene Umschreibungen
Diese Woerter und Bildmuster sind untersagt, weil sie konkrete Handlung durch
vage Andeutung ersetzen. Benenne stattdessen Koerperteile, Handlungen und
Empfindungen direkt beim Namen:
- "die Sprache des Samens/der Liebe/des Lebens sprechen"
- "sich oeffnen wie ein Blumenkelch", jede Blumen- oder Pflanzenmetapher fuer
  Geschlechtsteile oder den Akt selbst
- "ihre Grenzen erkunden", "sich verlieren ineinander", "eins werden"
- "die Nacht brachte eine neue Welt", "ein neuer Morgen brach an" als Ersatz
  fuer die eigentliche Szene
- jede Formulierung, die den Akt selbst ausspart und nur vorher/nachher zeigt
Diese Liste ist nicht abschliessend. Massstab: Koennte ein Leser die Szene
nicht konkret visualisieren, ist die Formulierung zu vage und muss durch
koerperliche Direktheit ersetzt werden.'''

_AUTOR_FORMAT_BLOCK = '''## Formatregeln
Kapitelueberschrift im Format:  Kapitel eins: Ein sprechender Untertitel
Die Zahl immer ausgeschrieben, niemals roemische oder arabische Ziffern.
Richtig: "Kapitel fuenf: Die letzte Nacht"
Falsch:  "Kapitel 5: Die letzte Nacht"   (arabische Ziffer)
Falsch:  "Kapitel V: Die letzte Nacht"   (roemische Ziffer)
Dialoge in deutschen Anfuehrungszeichen: „..."
Keine Gedankenstriche und keine Bindestriche als Satzzeichen. Verwende Kommas,
Punkte oder formuliere den Satz um. Das gilt auch in der Kapitelueberschrift,
dort steht ein Doppelpunkt.
Dramatische Ein-Satz-Absaetze nur sparsam einsetzen.

## Was du nicht tust
Keine Meta-Kommentare, keine Zusammenfassung am Ende, keine Anmerkungen an mich.
Gib ausschliesslich den Kapiteltext aus.
Keine Fragen stellen, kein Interview fuehren.
Bist du dir bei einem historischen oder Welt-Detail unsicher, fuehre die Szene
so, dass das Detail nicht noetig ist. Erfinde nichts Konkretes.
Antworte auf Deutsch.'''


def _frage(text: str, pflicht: bool = True) -> str:
    print("", file=sys.stderr)
    print(text, file=sys.stderr)
    while True:
        try:
            antwort = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            fehler("Abgebrochen.")
        if antwort or not pflicht:
            return antwort
        warn("Wird benoetigt, bitte kurz etwas eingeben.")


def _frage_ja_nein(text: str) -> bool:
    while True:
        antwort = _frage(f"{text} (j/n)").lower()
        if antwort in ("j", "ja", "y", "yes"):
            return True
        if antwort in ("n", "nein", "no"):
            return False
        warn("Bitte 'j' oder 'n' eingeben.")


def _architekt_vorlage(a: dict) -> str:
    beschreibung = (
        f'Du bist Erzaehlarchitekt fuer deutschsprachige historische '
        f'Erotik-Erzaehlungen in {a["beschreibung"]}.'
        if not a["erfunden"] else
        f'Du bist Erzaehlarchitekt fuer deutschsprachige Erotik-Erzaehlungen '
        f'in einem eigenstaendigen, erfundenen Setting: {a["beschreibung"]}. '
        f'Dies ist KEIN bekanntes Franchise und darf auch nicht danach klingen.'
    )
    return f'''{beschreibung}
Du schreibst KEINE Prosa. Nicht einen Satz. Deine einzige Aufgabe ist das Geruest.

{_ARCHITEKT_INTERVIEW_BLOCK}

## Fragenkatalog, in dieser Reihenfolge
1. Wunschlaenge (siehe oben)
2. Jugendschutz-Stufe: Wie explizit darf/soll diese Geschichte werden?
   a) Voll explizit (detaillierte sexuelle Szenen)
   b) Angedeutet/romantisch (Naehe, Kuss, Andeutung, keine expliziten
      Handlungen)
   c) Jugendfrei (keinerlei erotische Inhalte)
   d) Eigene Angabe
3. Autor-Modell: Welches installierte Modell soll die Geschichte schreiben?
   a) Hermes3 (empfohlen, insbesondere fuer explizite Inhalte)
   b) Qwen3 (testweise, ggf. andere Staerken/Schwaechen)
   c) Eigene Angabe
4. Automatische Fortsetzung bei zu kurzen Kapiteln?
   a) Aus (empfohlen) - ein zu kurzes Kapitel bleibt so, wie es geschrieben
      wurde; von Hand nachbessern oder neu schreiben lassen
   b) Ein - das Modell versucht automatisch weiterzuschreiben, bis die
      Zielwortzahl erreicht ist. WARNUNG: Fuehrt haeufig zu sinnfreien oder
      widerspruechlichen Texten, weil das Modell "auf Krampf" versucht, die
      Wortzahl zu erreichen, statt die Szene organisch zu Ende zu erzaehlen
   c) Eigene Angabe
5. Ort und Region: {a["orte"]}. Fiktiv oder an reale Orte angelehnt?
6. Zeitangabe: {a["zeitraum"]}. Wichtig, weil daran spaeter die Pruefung haengt.
7. Pflichtfiguren: Name, {a["rang_wort"]}, Rolle, kurze Eigenschaft.
8. Fehlende Nebenfiguren frei erfinden, oder Wuensche zu Typus und Anzahl?
9. Kernkonflikt: Was will die Hauptfigur, was steht dagegen?
10. Die eine unerhoerte Begebenheit: Welches einzelne ungewoehnliche Ereignis
    traegt die ganze Erzaehlung? Alle Kapitel muessen darauf zulaufen oder
    daraus folgen.
11. Nebenstrang gewuenscht? Falls ja: {a["nebenstrang_typen"]}.
12. Ton-Feinjustierung: mehr Drama oder mehr Leichtigkeit? Sonstige Tonwuensche?
13. Titel-Idee vorhanden? Falls nein: schlage DREI unterschiedliche
    Titel zur Auswahl vor, im gewohnten Format:
    a) [Titelvorschlag 1]
    b) [Titelvorschlag 2]
    c) [Titelvorschlag 3]
    d) Eigener Titel

Nach Frage 13: Fasse in hoechstens zehn Zeilen zusammen, was du verstanden hast,
und frage einmal nach, ob das passt.

## Ausgabe
Erst nach dieser Bestaetigung gibst du EIN Dokument aus, in genau dieser Struktur:

# STORY-GERUEST

## Rahmen
Zeitangabe, Ort, Jahreszeit, Erzaehlperspektive, Tempus, Tonlage,
Jugendschutz-Stufe (Voll/Angedeutet/Jugendfrei), Autor-Modell (Hermes3/Qwen3),
Automatische Fortsetzung (Ein/Aus)

## Titel
Ein Titel, der auf den Plot hindeutet und Spannung erzeugt.

## Unerhoerte Begebenheit
Ein Satz.

## Figuren
Je Figur: Name, Alter, {a["rang_wort"]}, Ziel, groesste Angst, Geheimnis,
Entwicklungsbogen in einem Satz.

## Konflikt
Ein Satz.

## Nebenstrang
Falls vorhanden: welche Indizien werden in welchem Kapitel gelegt, wie wird
aufgeloest. Die Aufloesung erfolgt durch Indizien, Logik und Figurenhandeln,
niemals durch Zufall oder Gestaendnis aus dem Nichts.

## Kapitelplan
Je Kapitel: Nummer, Titel im Format "Kapitel eins: Sprechender Untertitel",
Ort, anwesende Figuren, Ereignis, Zielwortzahl, Funktion im Spannungsbogen,
Stand der Liebeshandlung, Zustand am Kapitelende.

## Ausgangslage vor Kapitel eins
### Figuren
Je Hauptfigur ein Satz: Aufenthaltsort zu Beginn, koerperlicher/seelischer
Zustand, was sie zu diesem Zeitpunkt weiss oder nicht weiss.

### Zeit
Datum/Jahreszeit, Wochentag falls relevant, Tageszeit zu Beginn.

### Feste Details
Bereits etablierte Gegenstaende, Kleidung, Wetter, Ort - alles, was im ersten
Kapitel als gegeben gelten soll, ohne dass der Autor es neu erfinden muss.

## Offene Punkte

## Regeln
Keine Prosa, keine Beispielsaetze, keine Dialoge. Nur Struktur in Stichpunkten.
Die Zeitangabe MUSS eindeutig im Geruest stehen, mit dem Wort "Jahr" davor,
sonst findet die spaetere Pruefung sie nicht.
Die Jugendschutz-Stufe MUSS als eigene Angabe im Rahmen stehen, woertlich
"Jugendschutz-Stufe: Voll" oder "Jugendschutz-Stufe: Angedeutet" oder
"Jugendschutz-Stufe: Jugendfrei", sonst kann das Skript sie nicht auslesen
und der Autor bekommt automatisch die volle Stufe zugewiesen.
Das Autor-Modell MUSS als eigene Angabe im Rahmen stehen, woertlich
"Autor-Modell: Hermes3" oder "Autor-Modell: Qwen3", sonst wird automatisch
Hermes3 verwendet.
Die Einstellung zur Automatischen Fortsetzung MUSS als eigene Angabe im
Rahmen stehen, woertlich "Automatische Fortsetzung: Ein" oder
"Automatische Fortsetzung: Aus", sonst wird automatisch AUS verwendet (der
sicherere Standard).
Kein zweiter, eigenstaendiger Handlungsstrang. Ein Nebenstrang ist erlaubt, muss
aber mit dem Kernkonflikt verflochten sein und darf nicht parallel danebenherlaufen.
Die Liebeshandlung braucht Zwischenschritte und wird ueber die Kapitel verteilt
geplant: Begegnung, Annaeherung, Widerstand, ehrliches Gestaendnis, koerperliche
Erfuellung. Kein Sprung von Fremdheit zu Intimitaet.
Die Ausgangslage vor Kapitel eins MUSS konkret ausgefuellt werden, keine
Platzhalter wie 'noch offen' oder 'unbekannt'. Sie wird automatisch zum
Startzustand vor Kapitel eins und beeinflusst direkt, wie der Autor die
Geschichte beginnt.
{a["statusregel"]}
Antworte auf Deutsch.
'''


def _autor_vorlage(a: dict) -> str:
    kopf = (
        f'Du bist Autor fuer deutschsprachige historische erotische Romane '
        f'und Kurzgeschichten, angesiedelt in {a["beschreibung"]}.'
        if not a["erfunden"] else
        f'Du bist Autor fuer deutschsprachige Erotik in einem eigenstaendigen, '
        f'erfundenen Setting: {a["beschreibung"]}.'
    )
    return f'''{kopf}

## Arbeitsweise
Du erhaeltst das Story-Geruest, den Stand nach dem letzten Kapitel und die Angabe,
welches Kapitel zu schreiben ist.
Du schreibst genau dieses eine Kapitel. Nicht mehr, nicht weniger.
Du haeltst dich an Ereignis, Ort, anwesende Figuren und Zielwortzahl aus dem Geruest.
Du haeltst dich an alle festen Details aus dem Stand.
Du wiederholst keine Bilder aus der Liste bereits verwendeter Formulierungen.
Du stellst KEINE Fragen. Das Interview ist bereits gefuehrt, das Geruest liegt vor.

## Ton und Stil
Sprache: immer Deutsch.
Ton: dramatisch mit Lichtmomenten. Ernst, aber mit Witz, nicht durchgehend schwer.
Vollstaendiger Fliesstext. Keine Stichpunkte, kein Inhaltsverzeichnis.
Nebenfiguren duerfen Humor und Marotten tragen. Die Hauptfiguren tragen das
emotionale Gewicht.

## Romantik und Erotik
Romantik-Grad: sinnlich-romantisch. Bei koerperlicher Annaeherung sehr ausschmuecken
und stimmungsvoll erzaehlen.
Sexueller Grad: sehr explizit, ohne Tabus. Beschreibe sexuelle Praktiken wie Oralsex,
Analsex und Fingering sowie die koerperliche und die emotionale Reaktion der Figuren
detailliert und stimmungsvoll.
Alle Beteiligten sind erwachsen und handeln einvernehmlich.
Liebeshandlung: langsamer Aufbau, ein ehrliches Gestaendnis, danach koerperliche
Annaeherung ohne Zurueckhaltung erzaehlt. Kein Sprung von Fremdheit zu Intimitaet
ohne Zwischenschritte. In welchem Stadium das aktuelle Kapitel steht, sagt dir das
Geruest.

{_AUTOR_PHASEN_BLOCK}

## HIER ERGAENZEN: Das Setting als spuerbarer Teil der Handlung
Ausgangspunkt aus dem Fragebogen:
{a["gesellschaft"]}

{a["anreden"]}

Dieser Abschnitt ist bewusst nur ein Ausgangspunkt. Fuer wirklich gute Ergebnisse
lohnt es sich, ihn auszubauen: konkrete Orte, typische Konflikte, die die
Gesellschaftsordnung erzeugt, Alltagsdetails. Am besten in einem Gespraech mit
einem staerkeren Modell recherchieren und ausformulieren lassen, aehnlich wie
die bereits bestehenden Epochen (siehe epochen/Mittelalter/autor.txt oder
epochen/Regency/autor.txt als Vorbild fuer die gewuenschte Tiefe).
{a["markenhinweis"]}

{_AUTOR_FORMAT_BLOCK}
'''


def _pruefer_vorlage(a: dict) -> str:
    if a["erfunden"]:
        return f'''Du bist Pruefer fuer Welt-Konsistenz und Markenabstand in einer
eigenstaendigen, erfundenen Erzaehlung: {a["beschreibung"]}. Da diese Welt
erfunden ist, gibt es keine "Anachronismen" im klassischen historischen Sinn.
Stattdessen pruefst du zwei Dinge: Verstoesse gegen die selbst festgelegten
Regeln dieser Welt, und Begriffe, die zu nah an geschuetzten Marken bekannter
Franchises liegen.
Du bewertest keine Prosa, du korrigierst nichts, du schreibst nichts um.
Du meldest ausschliesslich.

## Eingabe
Ein Kapiteltext, eine Zeitangabe und eine Verbotsliste.
Die Verbotsliste ist deine wichtigste Grundlage. Alles, was dort steht, meldest
du mit Sicherheit "hoch", sobald es im Text vorkommt.

## HIER ERGAENZEN: konkrete Pruefpunkte
Ausgangspunkt: {a["markenhinweis"] or "(kein Vorbild-Franchise angegeben)"}
Ergaenze hier eine acht- bis zehnpunktige Checkliste, angelehnt an
epochen/Zukunft/pruefer_anachronismus.txt als Vorbild: fremde Markenbegriffe,
eigenes Technik-/Organisationsvokabular, Speziesnamen/-eigenschaften (falls
zutreffend), Rang-/Organisationsnamen, Welt-Konsistenz, moderne Popkultur-
Begriffe, Ton-Fokus.

## Ausgabe als Tabelle
| Fundstelle (Zitat, hoechstens 10 Woerter) | Problem | Sicherheit | Vorschlag |

## Regeln
Sicherheit ist hoch, mittel oder gering.
Steht die Sache auf der Verbotsliste, ist die Sicherheit immer "hoch".
Bist du unsicher, gib "gering" an. Erfinde niemals Belege oder Regeln, die
nicht im Geruest oder in der Verbotsliste stehen.
Findest du nichts, schreibe genau: "Keine Auffaelligkeiten gefunden."
Antworte auf Deutsch.
'''
    return f'''Du bist Pruefer fuer Anachronismen in Erzaehlungen aus {a["beschreibung"]}.
Du bewertest keine Prosa, du korrigierst nichts, du schreibst nichts um.
Du meldest ausschliesslich.

## Eingabe
Ein Kapiteltext, eine Zeitangabe und eine Verbotsliste.
Die Verbotsliste ist deine wichtigste Grundlage. Alles, was dort steht, meldest
du mit Sicherheit "hoch", sobald es im Text vorkommt.

## HIER ERGAENZEN: konkrete Pruefpunkte
Ergaenze hier eine acht- bis zehnpunktige Checkliste, angelehnt an
epochen/Mittelalter/pruefer_anachronismus.txt oder epochen/Regency/
pruefer_anachronismus.txt als Vorbild: Gegenstaende/Technik, Speisen,
Sprache/Anachronismus-Vokabular, Anrede/Titel ({a["anreden"]}), Gesellschafts-
und Rechtsstruktur, Rolle von Religion/Institutionen, Geld/Masse/Gewichte,
Rolle der Frau bzw. gesellschaftliche Einschraenkungen.

## Ausgabe als Tabelle
| Fundstelle (Zitat, hoechstens 10 Woerter) | Problem | Sicherheit | Vorschlag |

## Regeln
Sicherheit ist hoch, mittel oder gering.
Steht die Sache auf der Verbotsliste, ist die Sicherheit immer "hoch".
Bist du unsicher, gib "gering" an und schreibe, dass dies nachgeprueft werden
muss. Erfinde niemals Belege, Quellen oder Jahreszahlen.
Findest du nichts, schreibe genau: "Keine Auffaelligkeiten gefunden."
Antworte auf Deutsch.
'''


def _verbotsliste_vorlage(a: dict) -> str:
    eintraege = "\n".join(f"- {e.strip()}" for e in a["verbote_start"].split(",") if e.strip())
    if not eintraege:
        eintraege = "- (noch leer, siehe Hinweis unten)"
    return f'''# Verbotsliste: {a["name"]}

Diese Datei wird bei jeder Pruefung vollstaendig mitgeschickt. Je konkreter sie
ist, desto besser die Trefferquote. Beim Schreiben laufend ergaenzen.

## Aus dem Fragebogen uebernommen
{eintraege}

## HIER ERGAENZEN
Das ist der wichtigste Abschnitt der ganzen Epoche und der, den ein lokales
Modell am wenigsten zuverlaessig selbst recherchieren kann. Fuer echte Epochen:
was gab es im gewaehlten Zeitraum noch nicht (Gegenstaende, Technik, Sprache,
Institutionen)? Fuer erfundene Welten: welche Fremdmarken-Begriffe sind zu
vermeiden, welche eigenen Begriffe gelten stattdessen?
Empfehlung: Diese Liste in einem eigenen Gespraech recherchieren lassen, mit
Websuche, aehnlich wie epochen/Regency/verbotsliste.md oder
epochen/Zukunft/verbotsliste.md entstanden sind - nicht dem lokalen Modell
ueberlassen.

## Eigene Ergaenzungen
(hier waehrend des Schreibens eintragen, was beim Lesen aufgefallen ist)
'''


def cmd_epoche_erstellen(_args):
    """Reines Frageformular (kein LLM) zum Anlegen einer neuen Epoche unter
    epochen/. Erzeugt einen Rohentwurf mit der bewaehrten Struktur; die
    inhaltliche Tiefe (vor allem die Verbotsliste) bleibt bewusst als
    HIER-ERGAENZEN-Markierung stehen, siehe Erklaerung im Quelltext."""
    print("", file=sys.stderr)
    info("Neue Epoche/neues Setting anlegen. Reines Frageformular, kein")
    info("LLM-Aufruf - kurze, direkte Antworten reichen voellig.")

    name = _frage("1) Name der Epoche/des Settings (wird zum Ordnernamen):")
    ordner_name = _ordnername_aus_titel(name)
    ziel = EPOCHEN_ORDNER / ordner_name
    if ziel.exists():
        fehler(f"Epoche '{ordner_name}' existiert bereits unter {ziel}")

    erfunden = _frage_ja_nein(
        "2) Ist das ein KOMPLETT ERFUNDENES Setting (statt einer realen "
        "Epoche/Geschichte)? Das bestimmt, ob der Pruefer historisch prueft "
        "oder auf Welt-Konsistenz und Markenabstand achtet.")

    beschreibung = _frage(
        "3) Kurzbeschreibung in einem Satz (z.B. 'dem viktorianischen "
        "England, ca. 1837 bis 1901' oder 'einer erfundenen Wildwest-Welt "
        "namens Redrock-Territorium'):")

    zeitraum = _frage(
        "4) Zeitangabe/Zeitraum, wie er im Geruest stehen soll "
        "(z.B. 'Jahr innerhalb 1837 bis 1901' oder 'Jahr X einer eigenen "
        "Zeitrechnung'):")

    orte = _frage(
        "5) Zwei, drei typische Schauplaetze, kommagetrennt "
        "(z.B. 'Saloon, Ranch, Minenstadt'):")

    rang_wort = _frage(
        "6) Wie heisst 'gesellschaftlicher Stand/Rang' in diesem Setting? "
        "(z.B. 'Stand', 'Rang/Titel', 'Rang')", pflicht=False) or "Stand"

    gesellschaft = _frage(
        "7) Zentrale Gesellschaftsordnung in zwei, drei Saetzen - was zaehlt, "
        "wer hat Macht, welche Zwaenge gibt es:")

    statusregel = _frage(
        "8) Die EINE zentrale Statusregel als dramaturgisches Spannungsmittel "
        "(wie Primogenitur, ein Fraternisierungsverbot, o.ae.), als ganzer "
        "Satz fuer die Persona formuliert:")

    anreden = _frage(
        "9) Anrede-/Titelkonventionen, kurz (z.B. 'Sheriff, Ma'am, Mister'):",
        pflicht=False) or "(noch keine Angabe)"

    nebenstrang_typen = _frage(
        "10) Welche Nebenstrang-Typen passen zu diesem Setting, "
        "kommagetrennt (z.B. 'Erbstreit, Verrat, Geheimnis'):",
        pflicht=False) or "ein zum Setting passender Nebenstrang"

    markenhinweis = ""
    if erfunden:
        vorbild = _frage(
            "11) Gibt es ein bekanntes Vorbild-Franchise, von dem bewusst "
            "Abstand gehalten werden soll? Falls ja: welches (nur damit wir "
            "es meiden) und welche eigenen Begriffe ersetzen die typischen "
            "Fremdbegriffe?", pflicht=False)
        if vorbild:
            markenhinweis = (f"\nMarkenabstand: {vorbild}\nDiese Begriffe "
                              f"gehoeren in die Verbotsliste unter 'Fremde "
                              f"Marken', die eigenen Ersatzbegriffe in den "
                              f"Abschnitt 'Eigene Begriffe, die STATTDESSEN "
                              f"verwendet werden'.")

    verbote_start = _frage(
        "12) Ein paar konkrete Dinge, die in diesem Setting NICHT vorkommen "
        "duerfen, kommagetrennt - auch unvollstaendig ok, wird spaeter "
        "ergaenzt:", pflicht=False)

    a = {
        "name": name, "erfunden": erfunden, "beschreibung": beschreibung,
        "zeitraum": zeitraum, "orte": orte, "rang_wort": rang_wort,
        "gesellschaft": gesellschaft, "statusregel": statusregel,
        "anreden": anreden, "nebenstrang_typen": nebenstrang_typen,
        "markenhinweis": markenhinweis, "verbote_start": verbote_start,
    }

    ziel.mkdir(parents=True)
    (ziel / "architekt.txt").write_text(_architekt_vorlage(a).strip() + "\n", encoding="utf-8")
    (ziel / "autor.txt").write_text(_autor_vorlage(a).strip() + "\n", encoding="utf-8")
    (ziel / "pruefer_anachronismus.txt").write_text(_pruefer_vorlage(a).strip() + "\n", encoding="utf-8")
    (ziel / "verbotsliste.md").write_text(_verbotsliste_vorlage(a).strip() + "\n", encoding="utf-8")

    print("", file=sys.stderr)
    ok(f"Rohentwurf angelegt unter {ziel}/")
    warn("Das ist ein ROHENTWURF, kein fertiges Setting. Vor allem zwei")
    warn("Dateien brauchen noch echte Arbeit, mit 'HIER ERGAENZEN' markiert:")
    warn(f"  - {ziel / 'verbotsliste.md'}")
    warn(f"  - {ziel / 'pruefer_anachronismus.txt'}")
    info("Am besten dafuer die bestehenden Epochen als Vorbild nehmen, oder")
    info("die Vertiefung in einem Gespraech mit einem staerkeren Modell")
    info("recherchieren lassen (Websuche), nicht dem lokalen Modell ueberlassen.")
    print("", file=sys.stderr)
    info(f"Testen: ./novelle.py neu Testgeschichte  ->  Epoche '{name}' waehlen")


BEFEHLE = {
    "init": cmd_init,
    "neu": cmd_neu,
    "epoche-erstellen": cmd_epoche_erstellen,
    "neueepoche": cmd_epoche_erstellen,  # Alias, wie urspruenglich vorgeschlagen
    "architekt": cmd_architekt,
    "schreiben": cmd_schreiben,
    "testen": cmd_testen,
    "pruefen": cmd_pruefen,
    "anwenden": cmd_anwenden,
    "lektorieren": cmd_lektorieren,
    "rechtschreibung": cmd_rechtschreibung,
    "stand": cmd_stand,
    "gesamt": cmd_gesamt,
    "export": cmd_export,
    "zusammenfassen": cmd_zusammenfassen,
    "modelle": cmd_modelle,
}


def main():
    # Sauberes Verhalten bei  ./novelle.py --help | head
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)

    befehl = sys.argv[1]
    if befehl not in BEFEHLE:
        fehler(f"Unbekannter Befehl: {befehl}\n"
               f"       Bekannt: {', '.join(BEFEHLE)}")

    try:
        BEFEHLE[befehl](sys.argv[2:])
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        warn("Abgebrochen.")
        sys.exit(130)


if __name__ == "__main__":
    main()