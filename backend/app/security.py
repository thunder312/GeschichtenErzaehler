"""Verschluesselung von SSH-Zugangsdaten (Passwoerter, private Schluessel,
Passphrasen) fuer die Ablage in der lokalen SQLite-DB.

Zugangsdaten sollen nicht im Klartext auf der Platte liegen. Der Fernet-
Schluessel wird beim ersten Start einmalig erzeugt und lokal neben der
Datenbank abgelegt (siehe .gitignore - secret_key_path ist nicht
versioniert). Fuer Login-Passwoerter siehe stattdessen app/auth.py
(Argon2-Hashing, nicht reversibel wie Fernet hier).
"""
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet


def _lade_oder_erzeuge_schluessel(pfad: Path) -> bytes:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    if pfad.exists():
        return pfad.read_bytes()
    schluessel = Fernet.generate_key()
    pfad.write_bytes(schluessel)
    return schluessel


@lru_cache
def _fernet(secret_key_path: str) -> Fernet:
    return Fernet(_lade_oder_erzeuge_schluessel(Path(secret_key_path)))


def verschluesseln(klartext: str, secret_key_path: Path) -> bytes:
    return _fernet(str(secret_key_path)).encrypt(klartext.encode("utf-8"))


def entschluesseln(chiffrat: bytes, secret_key_path: Path) -> str:
    return _fernet(str(secret_key_path)).decrypt(chiffrat).decode("utf-8")
