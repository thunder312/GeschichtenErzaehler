"""Gemeinsame Hilfsfunktionen, die von mehreren API-Routern gebraucht werden:
Projektordner-Aufloesung und die Entscheidung, ob Ollama lokal oder ueber
einen SSH-Tunnel angesprochen wird.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException

from app import db
from app.config import Settings
from app.core import ssh_manager
from app.core.geruest import ordnername_aus_titel


def projekt_pfad(settings: Settings, ordner: str) -> Path:
    """Verhindert Path-Traversal (z.B. '../../etc') - der Ordnername muss
    ein direkter Unterordner von projects_dir sein und dort auch existieren."""
    kandidat = (settings.projects_dir / ordner).resolve()
    if settings.projects_dir.resolve() not in kandidat.parents and kandidat != settings.projects_dir.resolve():
        raise HTTPException(400, "Ungueltiger Projektordner.")
    if not kandidat.is_dir():
        raise HTTPException(404, f"Projekt '{ordner}' nicht gefunden.")
    return kandidat


def neuer_projekt_pfad(settings: Settings, titel: str) -> Path:
    name = ordnername_aus_titel(titel)
    ziel = settings.projects_dir / name
    zaehler = 2
    while ziel.exists():
        ziel = settings.projects_dir / f"{name}-{zaehler}"
        zaehler += 1
    return ziel


def ssh_ziel_aus_db(settings: Settings, ziel_id: str) -> ssh_manager.SSHZiel:
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    if row is None:
        raise HTTPException(404, "SSH-Ziel nicht gefunden.")
    geheimnis = db.ssh_ziel_geheimnis(row, settings.secret_key_path)
    return ssh_manager.SSHZiel(
        host=row["host"],
        port=row["port"],
        username=row["username"],
        auth_method=row["auth_method"],
        password=geheimnis.get("password"),
        private_key_pem=geheimnis.get("private_key_pem"),
        private_key_passphrase=geheimnis.get("passphrase"),
        remote_ollama_port=row["remote_ollama_port"],
    )


@contextmanager
def ollama_basis_url(settings: Settings, ssh_ziel_id: str | None):
    """Liefert eine base_url fuer app/core/ollama_client.py. Ohne ssh_ziel_id
    das lokal/per Umgebungsvariable konfigurierte Standard-Ollama, sonst ein
    frisch aufgebauter SSH-Tunnel zum hinterlegten Ziel."""
    if not ssh_ziel_id:
        yield settings.ollama_url
        return

    ziel = ssh_ziel_aus_db(settings, ssh_ziel_id)
    try:
        with ssh_manager.tunnel(ziel) as t:
            yield t.base_url
    except ssh_manager.SSHVerbindungsFehler as e:
        raise HTTPException(502, f"SSH-Verbindung fehlgeschlagen: {e}") from e
