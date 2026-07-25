#!/usr/bin/env python3
"""Legt einen neuen Benutzer-Account interaktiv an (Konsole: Benutzername +
Passwort-Abfrage). Bewusst KEIN HTTP-Endpunkt/keine Web-UI dafuer (siehe
ToDo.md Deployment) - Account-Anlage soll nicht oeffentlich erreichbar
sein, sondern erfordert direkten Zugriff auf den Server.

Aufruf (aus dem backend/-Ordner, funktioniert unter Windows genauso wie auf
dem spaeteren Linux-Server):

    python scripts/benutzer_anlegen.py
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.auth import passwort_hashen  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_db  # noqa: E402
from app.services import projekte_wurzel  # noqa: E402


def main() -> None:
    settings = get_settings()
    init_db(settings.database_path)

    username = input("Benutzername: ").strip()
    if not username:
        print("Abgebrochen: kein Benutzername eingegeben.")
        return
    if db.benutzer_by_username(settings.database_path, username):
        print(f"Fehler: Benutzer '{username}' existiert bereits.")
        return

    passwort = getpass.getpass("Passwort: ")
    wiederholung = getpass.getpass("Passwort (Wiederholung): ")
    if passwort != wiederholung:
        print("Abgebrochen: Passwoerter stimmen nicht ueberein.")
        return
    if len(passwort) < 8:
        print("Abgebrochen: Passwort sollte mindestens 8 Zeichen haben.")
        return

    ist_admin = input("Admin-Rechte? (j/N): ").strip().lower() in ("j", "ja", "y", "yes")

    benutzer_id = db.benutzer_anlegen(
        settings.database_path, username, passwort_hashen(passwort), ist_admin=ist_admin,
    )
    # Legt den Projektordner des Benutzers direkt an, damit er beim ersten
    # Login nicht leer/fehlend ist - gleiche Funktion, die auch zur
    # Laufzeit jeden Projekt-Pfad dieses Benutzers aufloest.
    ordner = projekte_wurzel(settings, username)

    print(f"Benutzer '{username}' angelegt (id={benutzer_id}, admin={ist_admin}).")
    print(f"Projektordner: {ordner}")


if __name__ == "__main__":
    main()
