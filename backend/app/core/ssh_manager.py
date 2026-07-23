"""SSH-Anbindung an entfernte Ollama-Server/Docker-Container.

Zwei Aufgaben (siehe Konzeptgespraech: KIs sollen ueber das Netzwerk
ansprechbar sein, bevorzugt auf Linux-Servern/Docker-Containern):

1. tunnel() oeffnet einen lokalen Port-Forward zum entfernten Ollama-Port.
   app/core/ollama_client.py spricht danach ganz normal HTTP gegen
   "http://127.0.0.1:<lokaler_port>" - der Client selbst weiss nichts von
   SSH.
2. exec_command() fuehrt einen Befehl auf dem entfernten Host aus (Pipe
   ueber stdin, stdout/stderr zurueck). Wird fuer hunspell gebraucht, das
   ein reines Linux-Kommandozeilentool ist und auf einer Windows-
   Entwicklungsmaschine lokal nicht existiert (siehe
   doc/Schnittstellen-Uebersicht.md Abschnitt 5.13).

Reine paramiko-Implementierung, kein externes ssh-Binary noetig.
"""
from __future__ import annotations

import io
import select
import shlex
import socketserver
import threading
from contextlib import contextmanager
from dataclasses import dataclass

import paramiko


class SSHVerbindungsFehler(Exception):
    pass


@dataclass
class SSHZiel:
    host: str
    port: int
    username: str
    auth_method: str  # "password" | "private_key" | "agent"
    password: str | None = None
    private_key_pem: str | None = None
    private_key_passphrase: str | None = None
    remote_ollama_port: int = 11434


def _lade_private_key(pem: str, passphrase: str | None) -> paramiko.PKey:
    fehler = []
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey):
        try:
            return cls.from_private_key(io.StringIO(pem), password=passphrase)
        except paramiko.SSHException as e:
            fehler.append(f"{cls.__name__}: {e}")
    raise SSHVerbindungsFehler(
        "Privater Schluessel konnte mit keinem unterstuetzten Format gelesen "
        "werden (Ed25519/RSA/ECDSA/DSS). Details: " + "; ".join(fehler)
    )


def _connect(ziel: SSHZiel, timeout: float = 15.0) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    pkey = None
    if ziel.auth_method == "private_key":
        if not ziel.private_key_pem:
            raise SSHVerbindungsFehler("Kein privater Schluessel hinterlegt.")
        pkey = _lade_private_key(ziel.private_key_pem, ziel.private_key_passphrase)

    try:
        client.connect(
            hostname=ziel.host,
            port=ziel.port,
            username=ziel.username,
            password=ziel.password if ziel.auth_method == "password" else None,
            pkey=pkey,
            timeout=timeout,
            allow_agent=(ziel.auth_method == "agent"),
            look_for_keys=False,
        )
    except paramiko.AuthenticationException as e:
        raise SSHVerbindungsFehler(f"Authentifizierung fehlgeschlagen: {e}") from e
    except (paramiko.SSHException, OSError) as e:
        raise SSHVerbindungsFehler(f"Verbindung zu {ziel.host}:{ziel.port} fehlgeschlagen: {e}") from e
    return client


def verbindung_testen(ziel: SSHZiel) -> tuple[bool, str]:
    try:
        client = _connect(ziel)
        transport = client.get_transport()
        server_version = transport.remote_version if transport else "unbekannt"
        client.close()
        return True, f"Verbindung erfolgreich ({server_version})."
    except SSHVerbindungsFehler as e:
        return False, str(e)


def exec_command(ziel: SSHZiel, cmd: list[str], stdin_text: str = "",
                  timeout: float = 30.0) -> tuple[int, str, str]:
    """Signatur kompatibel zu heuristik.ExecFn, damit z.B.
    functools.partial(exec_command, ziel) direkt als exec_fn fuer
    hunspell_unbekannte_woerter() dient."""
    client = _connect(ziel)
    try:
        befehl = " ".join(shlex.quote(teil) for teil in cmd)
        stdin, stdout, stderr = client.exec_command(befehl, timeout=timeout)
        if stdin_text:
            stdin.write(stdin_text)
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, out, err
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Lokaler Port-Forward (Tunnel) zum entfernten Ollama-Port
# ---------------------------------------------------------------------------

class _ForwardServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _handler_klasse(transport: paramiko.Transport, remote_host: str, remote_port: int):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                kanal = transport.open_channel(
                    "direct-tcpip", (remote_host, remote_port),
                    self.request.getpeername(),
                )
            except Exception:
                return
            if kanal is None:
                return
            try:
                while True:
                    lesbar, _, _ = select.select([self.request, kanal], [], [])
                    if self.request in lesbar:
                        daten = self.request.recv(4096)
                        if not daten:
                            break
                        kanal.send(daten)
                    if kanal in lesbar:
                        daten = kanal.recv(4096)
                        if not daten:
                            break
                        self.request.send(daten)
            finally:
                kanal.close()
                self.request.close()

    return Handler


class SSHTunnel:
    """Haelt eine SSH-Verbindung offen und leitet einen lokalen Port auf den
    entfernten Ollama-Port um. base_url ist danach ein ganz normales
    "http://127.0.0.1:<port>", das app/core/ollama_client.py ohne SSH-Wissen
    ansprechen kann."""

    def __init__(self, ziel: SSHZiel, local_port: int = 0):
        self._client = _connect(ziel)
        transport = self._client.get_transport()
        if transport is None:
            raise SSHVerbindungsFehler("Kein SSH-Transport verfuegbar.")
        handler = _handler_klasse(transport, "127.0.0.1", ziel.remote_ollama_port)
        self._server = _ForwardServer(("127.0.0.1", local_port), handler)
        self.local_port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._client.close()


@contextmanager
def tunnel(ziel: SSHZiel, local_port: int = 0):
    t = SSHTunnel(ziel, local_port)
    try:
        yield t
    finally:
        t.close()
