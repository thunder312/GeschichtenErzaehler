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
            "num_ctx": 8192,
            "num_predict": 4096,
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
            "repeat_penalty": 1.0,
            "presence_penalty": 1.5,
            "num_ctx": 16384,
            "num_predict": 6144,
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
    "anachronismen_korrektur": {
        "modell": "gemma4",
        "think": False,
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
}

GESAMT_NUM_CTX = 24576
GESAMT_NUM_PREDICT = 6144

# Drei feste Content-Stufen-Direktiven, die dem Autor-Prompt angehaengt
# werden (Architekten-Frage 2, siehe Bedienungsanleitung Abschnitt 8).
STUFE_DIREKTIVEN: dict[str, str] = {
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
