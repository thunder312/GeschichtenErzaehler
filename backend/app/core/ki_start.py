"""Ablauf "KI starten & Modelle scannen" fuer ein KI-Ziel (Button in den
Einstellungen): sorgt dafuer, dass Ollama auf dem Ziel antwortet - und liest
dann die dort installierten Modelle aus.

Schritte:
1. Antwortet Ollama schon? -> direkt scannen.
2. Sonst, falls das Ziel einen Steuer-Dienst hat: laeuft Docker? (sonst starten,
   auf dem Windows-PC startet der Dienst Docker Desktop), dann den Container
   "ollama" starten.
3. Auf Ollama warten, dann /api/tags lesen und gegen die Modelle abgleichen,
   die die Personas auf diesem Ziel brauchen.

Dieses Modul bleibt DB- und HTTP-framework-frei: alles Aeussere (Erreichbarkeit,
Steuer-Dienst, Modellliste) kommt als Funktion herein, siehe
app/api/ssh_targets.py fuer die Verdrahtung. Das macht den Ablauf ohne Docker
testbar."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

OLLAMA_CONTAINER = "ollama"
# Wie lange nach "docker start ollama" auf die API gewartet wird (der Container
# braucht ein paar Sekunden, bis Ollama lauscht).
OLLAMA_WARTEN_SEKUNDEN = 90.0
POLL_SEKUNDEN = 2.0


@dataclass
class KiStartHilfen:
    """Die aeusseren Faehigkeiten eines KI-Ziels. None = nicht vorhanden."""
    modelle_lesen: Callable[[], list[dict]]            # wirft bei "nicht erreichbar"
    steuer_status: Callable[[], dict] | None = None    # {"docker": bool|None, "containers": [...]}
    docker_starten: Callable[[], dict] | None = None
    container_starten: Callable[[str], dict] | None = None
    erwartete_modelle: Callable[[], list[str]] = lambda: []
    schlafen: Callable[[float], None] = time.sleep
    uhr: Callable[[], float] = time.monotonic


@dataclass
class KiStartErgebnis:
    erfolgreich: bool = False
    schritte: list[str] = field(default_factory=list)
    modelle: list[dict] = field(default_factory=list)
    fehlende_modelle: list[str] = field(default_factory=list)
    fehler: str | None = None


def _ohne_latest(name: str) -> str:
    return name[: -len(":latest")] if name.endswith(":latest") else name


def _fehlende(erwartet: list[str], vorhanden: list[dict]) -> list[str]:
    namen = {_ohne_latest(m["name"]) for m in vorhanden}
    fehlend: list[str] = []
    for e in erwartet:
        if _ohne_latest(e) not in namen and e not in fehlend:
            fehlend.append(e)
    return fehlend


def _erreichbar(h: KiStartHilfen) -> list[dict] | None:
    try:
        return h.modelle_lesen()
    except Exception:  # noqa: BLE001 - jeder Fehler heisst hier nur "noch nicht erreichbar"
        return None


def ki_starten(h: KiStartHilfen, schritt: Callable[[str], None] = lambda _t: None) -> KiStartErgebnis:
    """Fuehrt den Ablauf aus. `schritt` bekommt jede Fortschrittsmeldung sofort
    (fuer die Live-Anzeige); sie landen zusaetzlich in ergebnis.schritte."""
    erg = KiStartErgebnis()

    def melde(text: str) -> None:
        erg.schritte.append(text)
        schritt(text)

    def abschliessen(modelle: list[dict]) -> KiStartErgebnis:
        erg.modelle = modelle
        erg.fehlende_modelle = _fehlende(h.erwartete_modelle(), modelle)
        erg.erfolgreich = True
        melde(f"{len(modelle)} Modell(e) gefunden.")
        if erg.fehlende_modelle:
            melde("Fehlt auf diesem Ziel: " + ", ".join(erg.fehlende_modelle))
        return erg

    melde("Prüfe, ob Ollama antwortet …")
    modelle = _erreichbar(h)
    if modelle is not None:
        melde("Ollama läuft bereits.")
        return abschliessen(modelle)

    if h.steuer_status is None or h.container_starten is None:
        erg.fehler = (
            "Ollama antwortet nicht, und für dieses KI-Ziel ist kein Steuer-Dienst "
            "konfiguriert (Port + Token, siehe KI-Ziel bearbeiten). Bitte Docker/Ollama "
            "auf dem Zielrechner selbst starten."
        )
        melde(erg.fehler)
        return erg

    try:
        status = h.steuer_status()
    except Exception as e:  # noqa: BLE001
        erg.fehler = f"Steuer-Dienst nicht erreichbar: {e}"
        melde(erg.fehler)
        return erg

    if status.get("docker") is False:
        if h.docker_starten is None:
            erg.fehler = "Docker läuft auf dem Zielrechner nicht und lässt sich von hier nicht starten."
            melde(erg.fehler)
            return erg
        melde("Docker läuft nicht - starte Docker (kann bis zu 2 Minuten dauern) …")
        try:
            h.docker_starten()
        except Exception as e:  # noqa: BLE001
            erg.fehler = f"Docker starten fehlgeschlagen: {e}"
            melde(erg.fehler)
            return erg
        melde("Docker läuft.")

    laeuft = any(c.get("name") == OLLAMA_CONTAINER and c.get("running") for c in status.get("containers", []))
    if laeuft:
        melde("Container „ollama“ läuft, antwortet aber noch nicht - warte …")
    else:
        melde("Starte Container „ollama“ …")
        try:
            h.container_starten(OLLAMA_CONTAINER)
        except Exception as e:  # noqa: BLE001
            erg.fehler = f"Container „ollama“ starten fehlgeschlagen: {e}"
            melde(erg.fehler)
            return erg

    ende = h.uhr() + OLLAMA_WARTEN_SEKUNDEN
    while True:
        modelle = _erreichbar(h)
        if modelle is not None:
            melde("Ollama antwortet.")
            return abschliessen(modelle)
        if h.uhr() >= ende:
            erg.fehler = (
                f"Ollama antwortet {int(OLLAMA_WARTEN_SEKUNDEN)} s nach dem Start noch nicht. "
                "Bei GPU-Problemen hilft oft ein Neustart von Docker auf dem Zielrechner."
            )
            melde(erg.fehler)
            return erg
        h.schlafen(POLL_SEKUNDEN)
