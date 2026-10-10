#!/usr/bin/env python3
"""athene-steuerung — winziger HTTP-Dienst auf dem KI-Host.

Gibt dem Geschichten-Erzähler-Backend (das Prod nur über den Reverse-Tunnel
erreicht, ohne SSH) einen Weg, die Speicher-/Container-Lage auf Athene zu
sehen und die nicht beim Schreiben benötigten Bild-KI-Container zu
stoppen/starten. Feature "KI- und Speicherkontrolle".

Reine Standardbibliothek, keine Abhängigkeiten. Läuft an 127.0.0.1:<PORT>,
der Reverse-Tunnel bindet ihn auf Strato-127.0.0.1:18324.

Läuft auch auf dem Windows-PC (Docker Desktop): RAM kommt dann per ctypes,
und mit DOCKER_DESKTOP_EXE kann der Dienst Docker Desktop selbst starten.

Endpunkte (alle brauchen `Authorization: Bearer <token>`):
    GET  /status                             inkl. "docker": läuft der Docker-Daemon?
    POST /container/<name>/<start|stop>      name aus STEUERBARE_CONTAINER
    POST /docker/start                       Docker Desktop starten + warten (nur mit DOCKER_DESKTOP_EXE)

Umgebung:
    STEUERUNG_PORT        (7862)
    STEUERUNG_TOKEN_FILE  (./token)  Datei mit dem Bearer-Token (eine Zeile)
    STEUERUNG_TOKEN       alternativ der Token direkt
    STEUERBARE_CONTAINER  (sd-server,sd-server-pony,ollama)  Komma-Liste
    DOCKER_BIN            (docker)
    DOCKER_DESKTOP_EXE    (leer)  Pfad zu "Docker Desktop.exe" (nur Windows)
"""
from __future__ import annotations

import hmac
import json
import os
import re
import shutil
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("STEUERUNG_PORT", "7862"))
DOCKER = os.environ.get("DOCKER_BIN", "docker")
STEUERBAR = [c.strip() for c in os.environ.get(
    "STEUERBARE_CONTAINER", "sd-server,sd-server-pony,ollama").split(",") if c.strip()]
DOCKER_DESKTOP_EXE = os.environ.get("DOCKER_DESKTOP_EXE", "").strip()
DOCKER_START_WARTEN = 150.0


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


def _mem_windows() -> dict:
    """RAM/Auslagerungsdatei in MB über GlobalMemoryStatusEx (Windows-PC)."""
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    mb = 1024 * 1024
    ram_total, ram_avail = m.ullTotalPhys // mb, m.ullAvailPhys // mb
    # Das "PageFile" enthält den RAM mit; Auslagerung = Differenz.
    swap_total = max(0, (m.ullTotalPageFile - m.ullTotalPhys) // mb)
    swap_free = max(0, (m.ullAvailPageFile - m.ullAvailPhys) // mb)
    return {
        "ram": {"total_mb": ram_total, "available_mb": ram_avail,
                "used_mb": max(0, ram_total - ram_avail)},
        "swap": {"total_mb": swap_total, "used_mb": max(0, swap_total - swap_free)},
    }


def _mem() -> dict:
    """RAM/Swap in MB aus /proc/meminfo (kB-Werte); auf Windows per ctypes."""
    if not os.path.exists("/proc/meminfo"):
        return _mem_windows()
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


def _docker_laeuft() -> bool:
    try:
        code, _, _ = _run([DOCKER, "info"], timeout=20)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return code == 0


def docker_starten() -> dict:
    """Docker Desktop starten und warten, bis der Daemon antwortet. Nur wenn
    DOCKER_DESKTOP_EXE gesetzt ist (Windows); auf Linux läuft docker als Dienst."""
    if _docker_laeuft():
        return {"docker": True, "gestartet": False}
    if not DOCKER_DESKTOP_EXE:
        raise RuntimeError("Docker läuft nicht und DOCKER_DESKTOP_EXE ist nicht gesetzt")
    if not os.path.exists(DOCKER_DESKTOP_EXE):
        raise RuntimeError(f"Docker Desktop nicht gefunden: {DOCKER_DESKTOP_EXE}")
    subprocess.Popen([DOCKER_DESKTOP_EXE], close_fds=True)
    ende = time.monotonic() + DOCKER_START_WARTEN
    while time.monotonic() < ende:
        time.sleep(3)
        if _docker_laeuft():
            return {"docker": True, "gestartet": True}
    raise RuntimeError(f"Docker antwortet nach {int(DOCKER_START_WARTEN)} s noch nicht")


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
    d["docker"] = bool(laufend) or _docker_laeuft()
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
        if self.path.rstrip("/") == "/docker/start":
            try:
                return self._json(200, docker_starten())
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"fehler": str(e)})
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
