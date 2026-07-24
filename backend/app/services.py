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


def projekte_wurzel(settings: Settings) -> Path:
    """Wurzelverzeichnis aller Story-Projekte. Ohne in der DB gesetzten
    Override (siehe app/api/einstellungen.py) gilt Settings.projects_dir
    (Umgebungsvariable/Default) - mit Override der dort hinterlegte Pfad,
    damit der Speicherort ueber die GUI aenderbar ist, ohne das Backend neu
    zu starten."""
    override = db.einstellung_projects_dir_lesen(settings.database_path)
    pfad = Path(override) if override else settings.projects_dir
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def projekt_pfad(settings: Settings, ordner: str) -> Path:
    """Verhindert Path-Traversal (z.B. '../../etc') - der Ordnername muss
    ein direkter Unterordner der Projekte-Wurzel sein und dort auch
    existieren."""
    wurzel = projekte_wurzel(settings).resolve()
    kandidat = (wurzel / ordner).resolve()
    if wurzel not in kandidat.parents and kandidat != wurzel:
        raise HTTPException(400, "Ungueltiger Projektordner.")
    if not kandidat.is_dir():
        raise HTTPException(404, f"Projekt '{ordner}' nicht gefunden.")
    return kandidat


def neuer_projekt_pfad(settings: Settings, titel: str, epoche: str | None = None) -> Path:
    """Ort fuer ein neu anzulegendes Projekt. Ist die Einstellung
    "Unterordner je Epoche" aktiv (siehe app/api/einstellungen.py), landet
    das Projekt in einem nach der Epoche benannten Unterordner der
    Speicherort-Wurzel statt direkt darin - erspart das manuelle Umstellen
    des Speicherorts beim Wechsel zwischen Epochen."""
    wurzel = projekte_wurzel(settings)
    if epoche and db.einstellung_unterordner_je_epoche_lesen(settings.database_path):
        wurzel = wurzel / ordnername_aus_titel(epoche)
        wurzel.mkdir(parents=True, exist_ok=True)

    name = ordnername_aus_titel(titel)
    ziel = wurzel / name
    zaehler = 2
    while ziel.exists():
        ziel = wurzel / f"{name}-{zaehler}"
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
    das lokal/per Umgebungsvariable konfigurierte Standard-Ollama. Ist ein
    gespeichertes Ziel vom Typ 'direct' (kein SSH noetig, z.B. Ollama
    direkt im LAN oder auf einer anderen Windows-Maschine erreichbar), wird
    dessen hinterlegte Basis-URL direkt verwendet. Sonst ein frisch
    aufgebauter SSH-Tunnel zum hinterlegten Ziel."""
    if not ssh_ziel_id:
        yield settings.ollama_url
        return

    row = db.ssh_ziel_lesen(settings.database_path, ssh_ziel_id)
    if row is None:
        raise HTTPException(404, "KI-Ziel nicht gefunden.")

    if row["auth_method"] == "direct":
        yield row["host"]
        return

    ziel = ssh_ziel_aus_db(settings, ssh_ziel_id)
    try:
        with ssh_manager.tunnel(ziel) as t:
            yield t.base_url
    except ssh_manager.SSHVerbindungsFehler as e:
        raise HTTPException(502, f"SSH-Verbindung fehlgeschlagen: {e}") from e
