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
    favorit INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS einstellungen (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    projects_dir TEXT,
    unterordner_je_epoche INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS unnuetzes_wissen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kategorie TEXT NOT NULL,
    thema TEXT NOT NULL,
    kuriositaet TEXT NOT NULL,
    hintergrund TEXT NOT NULL,
    quelle TEXT
);

CREATE TABLE IF NOT EXISTS benutzer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    ist_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    benutzer_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY (benutzer_id) REFERENCES benutzer(id) ON DELETE CASCADE
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
        # Migration fuer vor der Favorit-Funktion angelegte Datenbanken -
        # CREATE TABLE IF NOT EXISTS legt die Spalte bei einer bereits
        # bestehenden Tabelle nicht nachtraeglich an.
        spalten = {r["name"] for r in conn.execute("PRAGMA table_info(ssh_targets)").fetchall()}
        if "favorit" not in spalten:
            conn.execute("ALTER TABLE ssh_targets ADD COLUMN favorit INTEGER NOT NULL DEFAULT 0")

        einstellungen_spalten = {r["name"] for r in conn.execute("PRAGMA table_info(einstellungen)").fetchall()}
        if "unterordner_je_epoche" not in einstellungen_spalten:
            conn.execute(
                "ALTER TABLE einstellungen ADD COLUMN unterordner_je_epoche INTEGER NOT NULL DEFAULT 0"
            )


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
            "remote_ollama_port, favorit, created_at, updated_at FROM "
            "ssh_targets ORDER BY favorit DESC, name"
        ).fetchall()


def ssh_ziel_favorit_setzen(db_path: Path, ziel_id: str, favorit: bool) -> None:
    """Es kann immer nur genau ein Favorit existieren - beim Setzen wird der
    Favorit-Status aller anderen Ziele deshalb zuerst geloescht."""
    with _verbindung(db_path) as conn:
        if favorit:
            conn.execute("UPDATE ssh_targets SET favorit=0")
        conn.execute(
            "UPDATE ssh_targets SET favorit=?, updated_at=? WHERE id=?",
            (1 if favorit else 0, _jetzt(), ziel_id),
        )


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


def einstellung_unterordner_je_epoche_lesen(db_path: Path) -> bool:
    with _verbindung(db_path) as conn:
        zeile = conn.execute("SELECT unterordner_je_epoche FROM einstellungen WHERE id=1").fetchone()
    return bool(zeile["unterordner_je_epoche"]) if zeile else False


def einstellung_unterordner_je_epoche_schreiben(db_path: Path, aktiv: bool) -> None:
    with _verbindung(db_path) as conn:
        conn.execute(
            "INSERT INTO einstellungen (id, unterordner_je_epoche) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET unterordner_je_epoche=excluded.unterordner_je_epoche",
            (1 if aktiv else 0,),
        )


def wissen_anzahl(db_path: Path) -> int:
    with _verbindung(db_path) as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM unnuetzes_wissen").fetchone()["n"]


def wissen_einfuegen(db_path: Path, eintraege: list[dict]) -> None:
    with _verbindung(db_path) as conn:
        conn.executemany(
            "INSERT INTO unnuetzes_wissen (kategorie, thema, kuriositaet, hintergrund, quelle) "
            "VALUES (:kategorie, :thema, :kuriositaet, :hintergrund, :quelle)",
            eintraege,
        )


def wissen_alle_lesen(db_path: Path) -> list[sqlite3.Row]:
    with _verbindung(db_path) as conn:
        return conn.execute(
            "SELECT id, kategorie, thema, kuriositaet, hintergrund, quelle FROM unnuetzes_wissen ORDER BY id"
        ).fetchall()


def benutzer_anlegen(db_path: Path, username: str, password_hash: str, ist_admin: bool = False) -> int:
    with _verbindung(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO benutzer (username, password_hash, ist_admin, created_at) "
            "VALUES (?, ?, ?, ?)",
            (username, password_hash, 1 if ist_admin else 0, _jetzt()),
        )
        return cur.lastrowid


def benutzer_by_username(db_path: Path, username: str) -> sqlite3.Row | None:
    with _verbindung(db_path) as conn:
        return conn.execute(
            "SELECT * FROM benutzer WHERE username=?", (username,)
        ).fetchone()


def benutzer_by_id(db_path: Path, benutzer_id: int) -> sqlite3.Row | None:
    with _verbindung(db_path) as conn:
        return conn.execute(
            "SELECT * FROM benutzer WHERE id=?", (benutzer_id,)
        ).fetchone()


def benutzer_alle_auflisten(db_path: Path) -> list[sqlite3.Row]:
    with _verbindung(db_path) as conn:
        return conn.execute(
            "SELECT id, username, ist_admin, created_at FROM benutzer ORDER BY username"
        ).fetchall()


def benutzer_loeschen(db_path: Path, benutzer_id: int) -> None:
    with _verbindung(db_path) as conn:
        # SQLite erzwingt FOREIGN KEY-Constraints nicht automatisch (PRAGMA
        # foreign_keys ist hier nicht gesetzt) - Sessions des Benutzers
        # deshalb explizit mitloeschen, sonst blieben verwaiste Zeilen in
        # der sessions-Tabelle zurueck.
        conn.execute("DELETE FROM sessions WHERE benutzer_id=?", (benutzer_id,))
        conn.execute("DELETE FROM benutzer WHERE id=?", (benutzer_id,))


def session_anlegen(db_path: Path, token: str, benutzer_id: int) -> None:
    with _verbindung(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (token, benutzer_id, created_at, last_seen_at) "
            "VALUES (?, ?, ?, ?)",
            (token, benutzer_id, _jetzt(), _jetzt()),
        )


def session_lesen(db_path: Path, token: str, max_age_tage: int = 30) -> sqlite3.Row | None:
    """Gibt den zugehoerigen Benutzer zurueck, wenn das Token existiert und
    seit last_seen_at nicht laenger als max_age_tage vergangen ist -
    andernfalls None (abgelaufen oder unbekannt)."""
    with _verbindung(db_path) as conn:
        zeile = conn.execute(
            "SELECT b.id, b.username, b.password_hash, b.ist_admin, b.created_at, "
            "s.last_seen_at FROM sessions s JOIN benutzer b ON b.id = s.benutzer_id "
            "WHERE s.token=?",
            (token,),
        ).fetchone()
    if zeile is None:
        return None
    letzte_aktivitaet = datetime.fromisoformat(zeile["last_seen_at"])
    if (datetime.now(timezone.utc) - letzte_aktivitaet).days > max_age_tage:
        return None
    return zeile


def session_beruehren(db_path: Path, token: str) -> None:
    with _verbindung(db_path) as conn:
        conn.execute("UPDATE sessions SET last_seen_at=? WHERE token=?", (_jetzt(), token))


def session_loeschen(db_path: Path, token: str) -> None:
    with _verbindung(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
