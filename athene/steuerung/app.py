#!/usr/bin/env python3
"""athene-steuerung — winziger HTTP-Dienst auf dem KI-Host.

Gibt dem Geschichten-Erzähler-Backend (das Prod nur über den Reverse-Tunnel
erreicht, ohne SSH) einen Weg, die Speicher-/Container-Lage auf Athene zu
sehen und die nicht beim Schreiben benötigten Bild-KI-Container zu
stoppen/starten. Feature "KI- und Speicherkontrolle".

Reine Standardbibliothek, keine Abhängigkeiten. Läuft an 127.0.0.1:<PORT>,
der Reverse-Tunnel bindet ihn auf Strato-127.0.0.1:18324.

Endpunkte (alle brauchen `Authorization: Bearer <token>`):
    GET  /status
    POST /container/<name>/<start|stop>      name aus STEUERBARE_CONTAINER

Umgebung:
    STEUERUNG_PORT        (7862)
    STEUERUNG_TOKEN_FILE  (./token)  Datei mit dem Bearer-Token (eine Zeile)
    STEUERUNG_TOKEN       alternativ der Token direkt
    STEUERBARE_CONTAINER  (sd-server,sd-server-pony)  Komma-Liste
    DOCKER_BIN            (docker)
"""
from __future__ import annotations

import hmac
import json
import os
import re
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("STEUERUNG_PORT", "7862"))
DOCKER = os.environ.get("DOCKER_BIN", "docker")
STEUERBAR = [c.strip() for c in os.environ.get(
    "STEUERBARE_CONTAINER", "sd-server,sd-server-pony").split(",") if c.strip()]


def _token() -> str:
    if os.environ.get("STEUERUNG_TOKEN"):
        return os.environ["STEUERUNG_TOKEN"].strip()
    pfad = os.environ.get("STEUERUNG_TOKEN_FILE",
                          os.path.join(os.path.dirname(__file__), "token"))
    with open(pfad, encoding="utf-8") as f:
        return f.read().strip()


TOKEN = _token()


def _run(cmd: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def _mem() -> dict:
    """RAM/Swap in MB aus /proc/meminfo (kB-Werte)."""
    werte: dict[str, int] = {}
    with open("/proc/meminfo", encoding="ascii") as f:
        for zeile in f:
            teile = zeile.split()
            if len(teile) >= 2 and teile[0].rstrip(":") in (
                "MemTotal", "MemAvailable", "SwapTotal", "SwapFree",
            ):
                werte[teile[0].rstrip(":")] = int(teile[1]) // 1024
    ram_total = werte.get("MemTotal", 0)
    ram_avail = werte.get("MemAvailable", 0)
    swap_total = werte.get("SwapTotal", 0)
    swap_free = werte.get("SwapFree", 0)
    return {
        "ram": {"total_mb": ram_total, "available_mb": ram_avail,
                "used_mb": max(0, ram_total - ram_avail)},
        "swap": {"total_mb": swap_total, "used_mb": max(0, swap_total - swap_free)},
    }


def _laufende_container() -> set[str]:
    code, out, _ = _run([DOCKER, "ps", "--format", "{{.Names}}"])
    return set(out.split()) if code == 0 else set()


def _ollama_ps() -> list[dict]:
    # `docker exec ollama ollama ps` -> Tabelle; tolerant parsen.
    code, out, _ = _run([DOCKER, "exec", "ollama", "ollama", "ps"])
    if code != 0:
        return []
    zeilen = [z for z in out.splitlines() if z.strip()]
    modelle = []
    for z in zeilen[1:]:  # Kopfzeile weg
        spalten = re.split(r"\s{2,}", z.strip())
        if spalten and spalten[0]:
            modelle.append({"name": spalten[0],
                            "processor": spalten[3] if len(spalten) > 3 else ""})
    return modelle


def status() -> dict:
    laufend = _laufende_container()
    d = _mem()
    d["containers"] = [{"name": n, "running": n in laufend} for n in STEUERBAR]
    d["ollama"] = _ollama_ps()
    return d


def container_setzen(name: str, aktion: str) -> dict:
    if name not in STEUERBAR:
        raise KeyError(name)
    if aktion not in ("start", "stop"):
        raise ValueError(aktion)
    code, out, err = _run([DOCKER, aktion, name], timeout=120)
    if code != 0:
        raise RuntimeError((err or out).strip() or f"docker {aktion} {name} fehlgeschlagen")
    return {"name": name, "aktion": aktion,
            "running": name in _laufende_container()}


class Handler(BaseHTTPRequestHandler):
    server_version = "athene-steuerung/1.0"

    def _json(self, code: int, obj: dict) -> None:
        rohdaten = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rohdaten)))
        self.end_headers()
        self.wfile.write(rohdaten)

    def _autorisiert(self) -> bool:
        kopf = self.headers.get("Authorization", "")
        erwartet = f"Bearer {TOKEN}"
        return hmac.compare_digest(kopf, erwartet)

    def log_message(self, *_args):  # ruhiger als der Default (steht sonst im journal)
        pass

    def do_GET(self):
        if not self._autorisiert():
            return self._json(401, {"fehler": "nicht autorisiert"})
        if self.path.rstrip("/") == "/status":
            try:
                return self._json(200, status())
            except Exception as e:  # noqa: BLE001 - Diagnose an den Aufrufer
                return self._json(500, {"fehler": str(e)})
        return self._json(404, {"fehler": "unbekannter Pfad"})

    def do_POST(self):
        if not self._autorisiert():
            return self._json(401, {"fehler": "nicht autorisiert"})
        m = re.fullmatch(r"/container/([A-Za-z0-9_.-]+)/(start|stop)", self.path.rstrip("/"))
        if not m:
            return self._json(404, {"fehler": "unbekannter Pfad"})
        name, aktion = m.group(1), m.group(2)
        try:
            return self._json(200, container_setzen(name, aktion))
        except KeyError:
            return self._json(403, {"fehler": f"Container '{name}' ist nicht steuerbar"})
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"fehler": str(e)})


def main() -> None:
    if not shutil.which(DOCKER):
        raise SystemExit(f"'{DOCKER}' nicht im PATH")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"athene-steuerung auf 127.0.0.1:{PORT}, steuerbar: {', '.join(STEUERBAR)}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
