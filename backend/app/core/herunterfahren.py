"""PC herunterfahren nach einem fertigen Automatik-Lauf (Option
"Danach PC herunterfahren" im Schreiben-Tab).

Nur sinnvoll, wenn das Backend lokal auf dem Windows-PC des Nutzers laeuft -
auf dem Strato-Server (Linux) ist die Option gar nicht verfuegbar
(moeglich() liefert dort False), damit nie versehentlich der Produktiv-Server
heruntergefahren wird. Windows' eigenes `shutdown /s /t N` liefert den
Vorlauf samt Abbruchmoeglichkeit (`shutdown /a`) frei Haus."""
from __future__ import annotations

import subprocess
import sys

VORLAUF_SEKUNDEN = 60


class HerunterfahrenFehler(Exception):
    pass


def moeglich() -> bool:
    return sys.platform == "win32"


def _shutdown(*argumente: str) -> None:
    if not moeglich():
        raise HerunterfahrenFehler("Herunterfahren wird nur unter Windows unterstützt.")
    try:
        ergebnis = subprocess.run(
            ["shutdown", *argumente], capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise HerunterfahrenFehler(str(e)) from e
    if ergebnis.returncode != 0:
        raise HerunterfahrenFehler((ergebnis.stderr or ergebnis.stdout or f"Exit-Code {ergebnis.returncode}").strip())


def planen(sekunden: int = VORLAUF_SEKUNDEN) -> None:
    _shutdown("/s", "/t", str(sekunden), "/c", "Geschichten Erzähler: Automatikmodus fertig - PC fährt herunter.")


def abbrechen() -> None:
    _shutdown("/a")
