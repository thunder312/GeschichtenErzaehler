"""SQLite-Persistenz fuer SSH-Ziele.

Bewusst die einzige "echte" Datenbank im System - Projektinhalte (Gerüst,
Kapitel, Befunde, ...) bleiben wie im CLI reine Markdown-Dateien (siehe
app/core/projekt_dateien.py). Nur Verbindungsdaten zu den entfernten
Ollama-Servern/Docker-Containern brauchen strukturierte, verschluesselte
Ablage.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.security import entschluesseln, verschluesseln

SCHEMA = """
CREATE TABLE IF NOT EXISTS ssh_targets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 22,
    username TEXT NOT NULL,
    auth_method TEXT NOT NULL,
    secret_encrypted BLOB,
    remote_ollama_port INTEGER NOT NULL DEFAULT 11434,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS einstellungen (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    projects_dir TEXT
);
"""


@contextmanager
def _verbindung(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with _verbindung(db_path) as conn:
        conn.executescript(SCHEMA)


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat()


def ssh_ziel_anlegen(db_path: Path, secret_key_path: Path, *, name: str, host: str,
                      port: int, username: str, auth_method: str,
                      geheimnis: dict, remote_ollama_port: int) -> str:
    """geheimnis enthaelt je nach auth_method: {'password': '...'} oder
    {'private_key_pem': '...', 'passphrase': '...'} oder {} bei 'agent'."""
    ziel_id = str(uuid.uuid4())
    verschluesselt = verschluesseln(json.dumps(geheimnis), secret_key_path)
    with _verbindung(db_path) as conn:
        conn.execute(
            "INSERT INTO ssh_targets (id, name, host, port, username, "
            "auth_method, secret_encrypted, remote_ollama_port, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ziel_id, name, host, port, username, auth_method, verschluesselt,
             remote_ollama_port, _jetzt(), _jetzt()),
        )
    return ziel_id


def ssh_ziel_aktualisieren(db_path: Path, secret_key_path: Path, ziel_id: str, *,
                            name: str, host: str, port: int, username: str,
                            auth_method: str, geheimnis: dict | None,
                            remote_ollama_port: int) -> None:
    with _verbindung(db_path) as conn:
        if geheimnis is not None:
            verschluesselt = verschluesseln(json.dumps(geheimnis), secret_key_path)
            conn.execute(
                "UPDATE ssh_targets SET name=?, host=?, port=?, username=?, "
                "auth_method=?, secret_encrypted=?, remote_ollama_port=?, "
                "updated_at=? WHERE id=?",
                (name, host, port, username, auth_method, verschluesselt,
                 remote_ollama_port, _jetzt(), ziel_id),
            )
        else:
            conn.execute(
                "UPDATE ssh_targets SET name=?, host=?, port=?, username=?, "
                "auth_method=?, remote_ollama_port=?, updated_at=? WHERE id=?",
                (name, host, port, username, auth_method, remote_ollama_port,
                 _jetzt(), ziel_id),
            )


def ssh_ziel_loeschen(db_path: Path, ziel_id: str) -> None:
    with _verbindung(db_path) as conn:
        conn.execute("DELETE FROM ssh_targets WHERE id=?", (ziel_id,))


def ssh_ziele_auflisten(db_path: Path) -> list[sqlite3.Row]:
    with _verbindung(db_path) as conn:
        return conn.execute(
            "SELECT id, name, host, port, username, auth_method, "
            "remote_ollama_port, created_at, updated_at FROM ssh_targets "
            "ORDER BY name"
        ).fetchall()


def ssh_ziel_lesen(db_path: Path, ziel_id: str) -> sqlite3.Row | None:
    with _verbindung(db_path) as conn:
        return conn.execute(
            "SELECT * FROM ssh_targets WHERE id=?", (ziel_id,)
        ).fetchone()


def ssh_ziel_geheimnis(row: sqlite3.Row, secret_key_path: Path) -> dict:
    if not row["secret_encrypted"]:
        return {}
    return json.loads(entschluesseln(row["secret_encrypted"], secret_key_path))


def einstellung_projects_dir_lesen(db_path: Path) -> str | None:
    """None bedeutet: kein Override gesetzt, es gilt der Standardpfad aus
    app/config.py (Settings.projects_dir)."""
    with _verbindung(db_path) as conn:
        zeile = conn.execute("SELECT projects_dir FROM einstellungen WHERE id=1").fetchone()
    return zeile["projects_dir"] if zeile else None


def einstellung_projects_dir_schreiben(db_path: Path, projects_dir: str | None) -> None:
    with _verbindung(db_path) as conn:
        conn.execute(
            "INSERT INTO einstellungen (id, projects_dir) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET projects_dir=excluded.projects_dir",
            (projects_dir,),
        )
