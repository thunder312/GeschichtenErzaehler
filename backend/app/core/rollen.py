"""Rollenkonfiguration - 1:1 aus pre-GUI/novelle.py uebernommen.

Wichtig (siehe doc/Schnittstellen-Uebersicht.md Abschnitt 4): Eine GUI, die
eigene Ollama-Aufrufe macht, soll diese Werte unveraendert uebernehmen, sonst
weicht das Verhalten vom bestehenden CLI ab. Kommentare zu einzelnen Werten
sind bewusst aus dem Original uebernommen, da sie die Begruendung fuer sonst
willkuerlich wirkende Parameter (z.B. think=False trotz denkfaehigem Modell)
enthalten.
"""

KEEP_ALIVE = "30m"

ROLLEN: dict[str, dict] = {
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
            # Der ganze bisherige Gespraechsverlauf wird bei jedem Zug neu
            # als eine einzige User-Nachricht mitgeschickt (siehe
            # app/core/architekt.py) UND die letzte Antwort muss im Erfolgs-
            # fall das komplette Story-Geruest (Rahmen, Figuren, Konflikt,
            # ausführlicher Kapitelplan, Ausgangslage, ...) enthalten - bei
            # einem langen Interview (viele Kapitel, ausfuehrliche
            # Nutzerantworten) plus "think": True-Denkanteil reichte das
            # alte 8192/4096-Budget nicht mehr aus und die Antwort wurde
            # mitten im Geruest abgeschnitten, aber trotzdem als fertig
            # gespeichert (siehe app/api/architekt.py:_zug, Vorfall
            # "Der-Preis-der-Wuerde-Ein-Geheimnis-in-Mayfair").
            "num_ctx": 24576,
            "num_predict": 8192,
            "seed": 42,
        },
    },
    "autor": {
        "modell": "hermes3:8b",
        "think": False,
        "optionen": {
            "temperature": 0.70,
            "top_p": 1.0,
            "min_p": 0.05,
            "top_k": 0,
            "repeat_penalty": 1.1,
            "repeat_last_n": 256,
            "num_ctx": 8192,
            "num_predict": 4096,
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
        "think": True,
        "optionen": {
            "temperature": 0.1,
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
            "num_predict": 6144,
            "seed": 42,
        },
    },
    # Dedizierter, bewusst extrem schmaler Pruefer NUR fuer Verb-Letzt-
    # Stellung in Nebensaetzen - ausgelagert aus "lektor", weil diese eine
    # Regel dort unter acht anderen Kategorien unterging und selbst von
    # groesseren/spezialisierten Modellen zuverlaessig uebersehen wurde
    # (siehe Session-Notizen zur Mars-Fluesterns-Geschichte). Gleiche
    # konservative Parameter wie die anderen Pruefer-Rollen.
    "satzbau": {
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
            "num_predict": 6144,
            "seed": 42,
        },
    },
    # Gleichberechtigte Autor-Alternative zu "autor" (Hermes3), waehlbar
    # ueber "Autor-Modell: Qwen3" im Geruest - siehe
    # app/core/geruest.py:autor_rolle_erkennen. Kein Test-/Vergleichsmodus,
    # sondern ein vollwertiger zweiter Schreiber.
    "autor_qwen": {
        "modell": "qwen3:14b",
        "think": False,
        "optionen": {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            # repeat_penalty stand vorher auf 1.0 (= wirkungslos) und
            # repeat_last_n fehlte ganz - presence_penalty allein bestraft
            # nur EINMAL benutzte Token unabhaengig von der Distanz, verhindert
            # aber keine exakt wiederholte TOKENFOLGE (siehe Vorfall
            # "Der-Preis-der-Wuerde-Ein-Geheimnis-in-Mayfair" Kapitel 9: ein
            # 6-Absatz-Block wurde 6x hintereinander wortgleich wiederholt,
            # bevorzugt in formelhaften expliziten Szenen). Werte jetzt wie
            # bei der "autor"-Rolle (Hermes3), die dasselbe Problem nicht
            # zeigt - siehe auch heuristik.py:interne_wiederholung_abschneiden
            # als zusaetzliches Sicherheitsnetz, falls es trotzdem passiert.
            "repeat_penalty": 1.1,
            "repeat_last_n": 256,
            "presence_penalty": 1.5,
            "num_ctx": 16384,
            "num_predict": 6144,
        },
    },
    # Extrahiert Figuren aus dem "## Figuren"-Abschnitt eines fertigen
    # Geruests fuer den Personen-Fundus (siehe app/core/fundus.py) - laeuft
    # nutzerweit statt projektweit, deshalb dieselben konservativen
    # Pruefer-Parameter wie "anachronismus"/"kontinuitaet" (niedrige
    # Temperatur, damit nichts hinzuerfunden wird).
    "fundus_pfleger": {
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
            "num_predict": 6144,
            "seed": 42,
        },
    },
    "lektor": {
        "modell": "gemma4",
        "think": False,
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
    # Fasst ein deutsches geruest.md zu einem kurzen, stichwortartigen
    # englischen Bildprompt fuer die Deckblatt-Generierung zusammen (siehe
    # app/core/bild_generierung.py). Bewusst niedrige Temperatur/kein
    # "think": das Modell soll nah am Gerüst bleiben statt kreativ
    # abzuweichen, und die Ausgabe ist kurz genug, dass ein Denkanteil nur
    # Zeit kostet, ohne die Qualitaet des Prompts zu verbessern.
    "cover_prompt": {
        "modell": "gemma4",
        "think": False,
        "optionen": {
            "temperature": 0.3,
            "top_p": 0.8,
            "min_p": 0.05,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "repeat_last_n": 64,
            "num_ctx": 16384,
            "num_predict": 300,
            "seed": 42,
        },
    },
}

GESAMT_NUM_CTX = 24576
GESAMT_NUM_PREDICT = 6144

# Drei feste Content-Stufen-Direktiven, die dem Autor-Prompt angehaengt
# werden (Architekten-Frage 2, siehe Bedienungsanleitung Abschnitt 8).
STUFE_DIREKTIVEN: dict[str, str] = {
    "voll": (
        "Content-Stufe für dieses Projekt: VOLL EXPLIZIT. Halte dich an die "
        "Vorgaben deiner Persona zu expliziter Erotik."
    ),
    "angedeutet": (
        "WICHTIG, Content-Stufe für dieses Projekt: ANGEDEUTET/ROMANTISCH. "
        "Ignoriere für dieses Projekt alle Anweisungen deiner Persona zu "
        "expliziten sexuellen Handlungen (Oralsex, Analsex, Fingering, "
        "detaillierte körperliche Beschreibung des Akts). Erlaubt sind "
        "Anziehung, Nähe, Kuss, Umarmung, angedeutete Zuneigung. Ein "
        "intimer Moment darf beginnen, wird aber VOR dem eigentlichen "
        "sexuellen Akt per Szenenwechsel, Ellipse oder gedämpfter Andeutung "
        "beendet, z.B. 'Er zog sie sanft zu sich, und die Kerze verlosch.' "
        "Keine expliziten Körperbeschreibungen sexueller Natur."
    ),
    "jugendfrei": (
        "WICHTIG, Content-Stufe für dieses Projekt: JUGENDFREI. Ignoriere "
        "für dieses Projekt VOLLSTÄNDIG alle Anweisungen deiner Persona zu "
        "Erotik oder Sexualität. Keine körperliche Intimität über "
        "Handhalten, eine Umarmung oder einen einzelnen, keuschen Kuss "
        "hinaus. Romantische Gefühle dürfen thematisiert werden, aber rein "
        "emotional, nie körperlich vertieft. Kein Bett, kein Entkleiden, "
        "keine sinnliche Beschreibung von Körpern."
    ),
}
