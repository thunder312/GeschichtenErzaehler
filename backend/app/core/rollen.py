"""Rollenkonfiguration - 1:1 aus pre-GUI/novelle.py uebernommen.

Wichtig (siehe doc/Schnittstellen-Uebersicht.md Abschnitt 4): Eine GUI, die
eigene Ollama-Aufrufe macht, soll diese Werte unveraendert uebernehmen, sonst
weicht das Verhalten vom bestehenden CLI ab. Kommentare zu einzelnen Werten
sind bewusst aus dem Original uebernommen, da sie die Begruendung fuer sonst
willkuerlich wirkende Parameter (z.B. think=False trotz denkfaehigem Modell)
enthalten.
"""

KEEP_ALIVE = "30m"

# Architekten-Interview: laengeres Keep-Alive als der Default. Zwischen zwei
# Fragen ueberlegt der Nutzer oft mehrere Minuten (kreative Entscheidung,
# Multiple-Choice abwaegen) - faellt das Modell in dieser Zeit aus dem
# Speicher (30m), kostet der naechste Zug einen kompletten Kaltstart samt
# Prefill des gesamten bisherigen Gespraechsverlaufs. Gilt fuer beide
# Interview-Rollen ("architekt_frage" fuer die Fragen, "architekt" fuer die
# einmalige Geruest-Synthese am Schluss).
KEEP_ALIVE_INTERVIEW = "2h"

# Gemeinsame Sampling-Parameter fuer beide Interview-Rollen - "architekt_frage"
# (jeder Frage-Zug, schlank) und "architekt" (nur der finale Geruest-Zug)
# sollen sich im Gespraechston nicht unterscheiden.
_ARCHITEKT_SAMPLING = {
    "temperature": 0.4,
    "top_p": 0.9,
    "min_p": 0.05,
    "top_k": 40,
    "repeat_penalty": 1.05,
    "repeat_last_n": 64,
    "seed": 42,
}

ROLLEN: dict[str, dict] = {
    # Jeder einzelne Frage-Zug des Architekten-Interviews (siehe
    # app/api/architekt.py:_zug). Bewusst schlank gehalten, weil das die
    # eigentliche Engstelle ist - der Nutzer wartet zwischen JEDER Frage:
    # - think=False: fuer eine Multiple-Choice-Rueckfrage bringt ein
    #   versteckter Reasoning-Block nichts ausser CPU-Generierungszeit, die
    #   als "denkt nach..." abgesessen wird.
    # - num_ctx=8192 statt 32768: auf CPU-Inferenz (Athene) skaliert die
    #   Prefill-Zeit mit der ALLOZIERTEN Kontextgroesse, nicht nur mit der
    #   echten Promptlaenge (siehe "analysator"-Kommentar unten). Ein
    #   laufendes Interview hat selten mehr als 2-3k Token Verlauf.
    # - num_predict=1024: eine Frage samt Optionen ist kurz; reicht auch,
    #   um den "# STORY-GERUEST"-Praefix zu erkennen, wenn das Modell hier
    #   ins Finale kippt (_zug wiederholt diesen einen Zug dann mit der
    #   vollen "architekt"-Rolle).
    # Das Modell kann unter "KI-Ziele -> Persona-Modell-Zuordnung" separat
    # auf ein kleineres, noch schnelleres getauscht werden.
    "architekt_frage": {
        "modell": "gemma4",
        "think": False,
        "keep_alive": KEEP_ALIVE_INTERVIEW,
        "optionen": {
            **_ARCHITEKT_SAMPLING,
            "num_ctx": 8192,
            "num_predict": 1024,
        },
    },
    "architekt": {
        "modell": "gemma4",
        "think": True,
        "keep_alive": KEEP_ALIVE_INTERVIEW,
        "optionen": {
            **_ARCHITEKT_SAMPLING,
            # Diese Rolle laeuft NUR noch fuer den einen finalen Zug, der das
            # komplette Story-Geruest erzeugt (siehe app/api/architekt.py:_zug -
            # die Frage-Zuege davor nutzen "architekt_frage"). Der ganze
            # bisherige Gespraechsverlauf wird als eine User-Nachricht
            # mitgeschickt UND die Antwort muss das komplette Geruest (Rahmen,
            # Figuren, Konflikt, ausführlicher Kapitelplan, Ausgangslage, ...)
            # enthalten - bei einem langen Interview plus "think": True-Denk-
            # anteil reichte das alte 8192/4096-Budget nicht (abgeschnittenes
            # Geruest, trotzdem als fertig gespeichert - Vorfall
            # "Der-Preis-der-Wuerde-Ein-Geheimnis-in-Mayfair").
            # Zweiter Vorfall (2026-08-19, "Japanisches-Hochmittelalter/neu"):
            # ein offline ausgefuelltes Vorlage-Dokument (siehe
            # arch.erste_eingabe_mit_vorlage) kann so vollstaendig sein, dass
            # der Architekt OHNE Rueckfrage direkt das komplette Geruest ausgibt
            # (sechs Kapitel, vier Figuren, Nebenstrang, plus Denkanteil) -
            # sprengte selbst das verdoppelte Retry-Budget (16384). 24576/8192
            # auf 32768/12288 erhoeht, das Retry-Budget (Verdopplung in _zug())
            # bleibt unterhalb von num_ctx, damit fuer den Prompt (Persona +
            # Vorlage-Text + Verlauf) genug Platz bleibt.
            "num_ctx": 32768,
            "num_predict": 12288,
        },
    },
    # Einziger Schreiber (Stand 2026-08-13): Hermes3 und Qwen3 wurden als
    # Autor-Alternativen entfernt, seit Mistral sich als klar ueberlegen
    # erwiesen hat - kein Auswahlfeld im Architekten-Interview mehr, siehe
    # app/core/geruest.py:autor_rolle_erkennen (liefert immer "autor").
    # Modell+Optionen von der ehemaligen Rolle "autor_mistral" uebernommen,
    # inklusive der dort per Live-Lauf gefundenen presence_penalty-Tuning-
    # Historie (siehe Kommentar unten).
    #
    # presence_penalty stand beim ersten Live-Lauf ("Das-Echo-der-
    # Verpflichtung-Ein-Geheimnis-in-Winterbottom-Hall") noch bei 1.5 (1:1
    # von der damaligen "autor_qwen"-Rolle uebernommen) - mistral-small3.2
    # brach damit ab Kapitel 2 systematisch weit vor der Zielwortzahl UND
    # mitten im Satz ab (alle Kapitel nur 29-36% des Ziels statt der bei
    # Hermes3/Qwen3 ueblichen ~100%). Ein so aggressiver presence_penalty
    # bestraft bei jedem neu benutzten Token zusaetzlich zum repeat_penalty
    # noch einmal jedes bereits verwendete - bei diesem Modell offenbar
    # stark genug, um frueh einen Stop-Token statt der naechsten Szene zu
    # waehlen. Auf 0.4 gesenkt (deutlich milder), repeat_penalty/
    # repeat_last_n bleiben als primaerer Schutz gegen Wiederholungsschleifen
    # erhalten.
    "autor": {
        "modell": "mistral-small3.2:latest",
        "think": False,
        "optionen": {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "repeat_penalty": 1.1,
            "repeat_last_n": 256,
            "presence_penalty": 0.4,
            "num_ctx": 16384,
            "num_predict": 6144,
        },
    },
    # Analysator (siehe app/core/analysator.py, ToDo.md "groesseres Feature
    # als neuen Haupt-Tab"): liest importierten Fremdtext (bestehende
    # Geschichte/Novelle) kapitelweise und fasst ihn am Ende zu einem
    # kompletten Story-Geruest zusammen, damit die Geschichte als Projekt
    # zum Neu-Schreiben verfuegbar wird. Bewusst dasselbe Modell wie "autor"
    # (explizite Vorgabe: "Analysator (powered by Mistral)") statt gemma4
    # wie beim Architekten - bleibt so im selben Modell-Oekosystem wie der
    # spaetere Neu-Schreiben-Durchlauf. Niedrigere Temperatur als "autor"
    # (0.3 statt 0.7): Aufgabe ist FAKTEN aus vorgegebenem Text extrahieren,
    # nicht frei erzaehlen - zu kreativ wuerde Ereignisse/Figuren erfinden,
    # die im Originaltext gar nicht vorkommen.
    # num_ctx bewusst NICHT groesser als "autor" (16384, nicht z.B. 24576):
    # ein Live-Test gegen das CPU-only KI-Ziel "Athene" (siehe [[ssh-ziel-
    # athene]]) brauchte fuer einen einzigen, sehr kurzen Kapitel-Analyse-
    # Aufruf (~220 Woerter Eingabe) ueber 18 Minuten bei num_ctx=24576 - ein
    # erster testweise gesenkter Wert auf 16384 (identisch zu "autor", das
    # in echten Automatik-Laeufen auf derselben Hardware bereits akzeptabel
    # lief) ist der naheliegendste Hebel, da CPU-Inferenz die Praefill-Zeit
    # tendenziell mit der ALLOZIERTEN Kontextgroesse skaliert, nicht nur mit
    # der tatsaechlichen Prompt-Laenge. Noch nicht erneut live verifiziert -
    # falls weiterhin sehr langsam, ist das ein reines Hardware-/Ollama-
    # Performance-Thema auf Athene, kein Logikfehler in diesem Modul.
    "analysator": {
        "modell": "mistral-small3.2:latest",
        "think": False,
        "optionen": {
            "temperature": 0.3,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "repeat_penalty": 1.1,
            "repeat_last_n": 128,
            "num_ctx": 16384,
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
    # Fasst bei einem Konflikt-Fund (mehrere Pruefer mit sich widersprechenden
    # Vorschlaegen fuer dieselbe Textstelle, siehe app/core/befunde_merge.py)
    # deren Anmerkungen+Einzelvorschlaege per gezieltem, vom Nutzer per Klick
    # ausgeloestem Aufruf zu EINEM gemeinsamen Ersatztext zusammen - siehe
    # app/api/pipeline.py:befund_synthese() und app/core/geruest.py:
    # BEFUND_SYNTHESE_SYSTEM. Gleiche konservative Parameter wie "lektor"
    # (niedrige Temperatur, kein "think"): die Aufgabe ist eine nahe am
    # Original bleibende Textkorrektur, kein kreatives Neuschreiben.
    "befund_synthese": {
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
            "num_predict": 1024,
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
    # Beantwortet Nutzerfragen ZU einer laufenden Geschichte (siehe
    # app/core/geruest.py:STORY_FRAGE_SYSTEM, app/api/pipeline.py:
    # story_frage) - niedrige Temperatur/kein "think" aus demselben Grund
    # wie bei "cover_prompt": die Antwort soll nah am mitgelieferten
    # Gerüst/Stand bleiben statt kreativ zu ergaenzen.
    "story_frage": {
        "modell": "gemma4",
        "think": False,
        "optionen": {
            "temperature": 0.2,
            "top_p": 0.85,
            "min_p": 0.05,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "repeat_last_n": 64,
            "num_ctx": 16384,
            "num_predict": 1024,
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
