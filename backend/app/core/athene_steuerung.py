"""Client für den `athene-steuerung`-Dienst auf dem KI-Host (Feature
"KI- und Speicherkontrolle", siehe athene/steuerung/app.py).

Zweck: beim Start des Schreibens die Speicher-/Container-Lage auf dem KI-Host
abfragen und nicht benötigte Bild-KI-Container herunterfahren, damit dem
24B-Autor genug RAM bleibt (sonst rechnet er aus dem Swap, siehe
athene/README.md → Troubleshooting).

Zwei Transportwege, gleiche normalisierte Rückgabe:
- **HTTP** gegen den `athene-steuerung`-Dienst (Bearer-Token) - für 'direct'-
  KI-Ziele, die nur über den Reverse-Tunnel erreichbar sind (Prod).
- **SSH** `exec_command` (`free`/`docker`) - für echte SSH-Ziele (Dev-LAN),
  die keinen Steuer-Dienst brauchen.

Dieses Modul bleibt DB-frei (siehe app/services.py für die Auflösung aus der
ssh_targets-Tabelle + den Einstellungen)."""
from __future__ import annotations

import json
import re

import httpx

from app.core import ssh_manager
from app.core.ssh_manager import SSHZiel

HTTP_TIMEOUT = 20.0
CONTAINER_TIMEOUT = 130.0


class SteuerFehler(Exception):
    """KI-Host-Steuerung nicht verfügbar oder Aktion fehlgeschlagen."""


# ---------------------------------------------------------------------------
# Normalisierte Rückgabe
# ---------------------------------------------------------------------------

def _leerer_status(container_namen: list[str]) -> dict:
    return {
        "verfuegbar": False,
        "ram": {"total_mb": 0, "available_mb": 0, "used_mb": 0},
        "swap": {"total_mb": 0, "used_mb": 0},
        "containers": [{"name": n, "running": False} for n in container_namen],
        "ollama": [],
    }


def _status_aus_dienst(rohdaten: dict, container_namen: list[str]) -> dict:
    """Antwort des athene-steuerung-Dienstes auf die vom Backend
    konfigurierte Containerliste eindampfen (der Dienst hat seine eigene
    Whitelist, die Listen müssen nicht identisch sein)."""
    laufend = {c["name"]: bool(c.get("running")) for c in rohdaten.get("containers", [])}
    return {
        "verfuegbar": True,
        "ram": rohdaten.get("ram", {"total_mb": 0, "available_mb": 0, "used_mb": 0}),
        "swap": rohdaten.get("swap", {"total_mb": 0, "used_mb": 0}),
        "containers": [{"name": n, "running": laufend.get(n, False)} for n in container_namen],
        "ollama": rohdaten.get("ollama", []),
    }


# ---------------------------------------------------------------------------
# HTTP-Weg (direct-Ziele über den Reverse-Tunnel)
# ---------------------------------------------------------------------------

def _http_kopf(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fehlertext(antwort: httpx.Response) -> str:
    try:
        return str(antwort.json().get("fehler") or antwort.text)
    except (ValueError, TypeError):
        return antwort.text or f"HTTP {antwort.status_code}"


def status_ueber_http(steuer_url: str, token: str, container_namen: list[str]) -> dict:
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            antwort = client.get(f"{steuer_url.rstrip('/')}/status", headers=_http_kopf(token))
    except httpx.HTTPError as e:
        raise SteuerFehler(f"Steuer-Dienst nicht erreichbar: {e}") from e
    if antwort.status_code >= 400:
        detail = _fehlertext(antwort)
        raise SteuerFehler(f"Status-Abfrage fehlgeschlagen (HTTP {antwort.status_code}): {detail}")
    return _status_aus_dienst(antwort.json(), container_namen)


def container_ueber_http(steuer_url: str, token: str, name: str, aktion: str) -> dict:
    try:
        with httpx.Client(timeout=CONTAINER_TIMEOUT) as client:
            antwort = client.post(
                f"{steuer_url.rstrip('/')}/container/{name}/{aktion}", headers=_http_kopf(token),
            )
    except httpx.HTTPError as e:
        raise SteuerFehler(f"Steuer-Dienst nicht erreichbar: {e}") from e
    if antwort.status_code >= 400:
        raise SteuerFehler(f"{aktion} {name} fehlgeschlagen: {_fehlertext(antwort)}")
    return antwort.json()


# ---------------------------------------------------------------------------
# SSH-Weg (echte SSH-Ziele, z.B. Dev-LAN)
# ---------------------------------------------------------------------------

_STATUS_SKRIPT = r"""
cat /proc/meminfo | grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):'
echo '---DOCKER---'
docker ps --format '{{.Names}}'
echo '---OLLAMA---'
docker exec ollama ollama ps 2>/dev/null || true
"""


def _meminfo_mb(text: str) -> dict:
    werte: dict[str, int] = {}
    for zeile in text.splitlines():
        teil = zeile.split()
        if len(teil) >= 2 and teil[0].rstrip(":") in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            werte[teil[0].rstrip(":")] = int(teil[1]) // 1024
    rt, ra = werte.get("MemTotal", 0), werte.get("MemAvailable", 0)
    st, sf = werte.get("SwapTotal", 0), werte.get("SwapFree", 0)
    return {
        "ram": {"total_mb": rt, "available_mb": ra, "used_mb": max(0, rt - ra)},
        "swap": {"total_mb": st, "used_mb": max(0, st - sf)},
    }


def _ollama_ps_parsen(text: str) -> list[dict]:
    zeilen = [z for z in text.splitlines() if z.strip()]
    modelle = []
    for z in zeilen[1:]:
        spalten = re.split(r"\s{2,}", z.strip())
        if spalten and spalten[0]:
            modelle.append({"name": spalten[0], "processor": spalten[3] if len(spalten) > 3 else ""})
    return modelle


def status_ueber_ssh(ziel: SSHZiel, container_namen: list[str]) -> dict:
    try:
        code, out, err = ssh_manager.exec_command(ziel, ["bash", "-lc", _STATUS_SKRIPT])
    except ssh_manager.SSHVerbindungsFehler as e:
        raise SteuerFehler(f"SSH zum KI-Host fehlgeschlagen: {e}") from e
    if code != 0 and not out:
        raise SteuerFehler(f"Status-Abfrage fehlgeschlagen: {err.strip() or 'kein Ergebnis'}")

    mem_teil, _, rest = out.partition("---DOCKER---")
    docker_teil, _, ollama_teil = rest.partition("---OLLAMA---")
    laufend = set(docker_teil.split())
    d = _meminfo_mb(mem_teil)
    d["verfuegbar"] = True
    d["containers"] = [{"name": n, "running": n in laufend} for n in container_namen]
    d["ollama"] = _ollama_ps_parsen(ollama_teil)
    return d


def container_ueber_ssh(ziel: SSHZiel, name: str, aktion: str) -> dict:
    if aktion not in ("start", "stop"):
        raise SteuerFehler(f"Unbekannte Aktion '{aktion}'.")
    try:
        code, out, err = ssh_manager.exec_command(
            ziel, ["docker", aktion, name], timeout=CONTAINER_TIMEOUT,
        )
    except ssh_manager.SSHVerbindungsFehler as e:
        raise SteuerFehler(f"SSH zum KI-Host fehlgeschlagen: {e}") from e
    if code != 0:
        raise SteuerFehler(f"{aktion} {name} fehlgeschlagen: {(err or out).strip()}")
    try:
        _, laufend, _ = ssh_manager.exec_command(ziel, ["docker", "ps", "--format", "{{.Names}}"])
        running = name in laufend.split()
    except ssh_manager.SSHVerbindungsFehler:
        running = aktion == "start"
    return {"name": name, "aktion": aktion, "running": running}


# ---------------------------------------------------------------------------
# Heuristik: lohnt ein Herunterfahren?
# ---------------------------------------------------------------------------

def herunterfahren_empfohlen(status: dict) -> bool:
    """True, wenn mindestens einer der überwachten Container läuft UND der
    Host unter Speicherdruck steht (Swap in Benutzung oder < 6 GB RAM frei) -
    nur dann lohnt der Vorschlag, den Nutzer beim Schreibstart zu fragen."""
    laufen = any(c["running"] for c in status.get("containers", []))
    if not laufen:
        return False
    swap_benutzt = status.get("swap", {}).get("used_mb", 0) > 200
    ram_knapp = status.get("ram", {}).get("available_mb", 0) < 6144
    return swap_benutzt or ram_knapp


__all__ = [
    "SteuerFehler",
    "status_ueber_http", "container_ueber_http",
    "status_ueber_ssh", "container_ueber_ssh",
    "herunterfahren_empfohlen",
]
