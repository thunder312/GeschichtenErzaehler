"""Benutzerverwaltung fuer Admin-Benutzer (siehe ToDo.md Deployment) - loest
das bisherige Konsolenskript scripts/benutzer_anlegen.py fuer den laufenden
Betrieb ab, das fuer die Erstanlage des allerersten Admin-Accounts weiterhin
nuetzlich bleibt (bevor ueberhaupt ein Login existiert, mit dem man sich in
dieser GUI anmelden koennte).

Der gesamte Router ist in app/main.py mit Depends(get_current_admin)
eingebunden - nur Admin-Benutzer duerfen hier ueberhaupt etwas sehen oder
aendern (siehe Aufgabe 2: Tab "Benutzer" nur fuer Admins sichtbar)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.auth import get_current_user, passwort_hashen
from app.config import Settings, get_settings
from app.schemas import Benutzer, BenutzerAnlegenAnfrage, BenutzerEintrag
from app.services import benutzer_projekte_uebertragen, projekte_wurzel

router = APIRouter(prefix="/api/benutzer", tags=["benutzer"])


@router.get("", response_model=list[BenutzerEintrag])
def liste(settings: Settings = Depends(get_settings)):
    zeilen = db.benutzer_alle_auflisten(settings.database_path)
    return [BenutzerEintrag(**dict(z)) for z in zeilen]


@router.post("", response_model=BenutzerEintrag, status_code=201)
def anlegen(anfrage: BenutzerAnlegenAnfrage, settings: Settings = Depends(get_settings)):
    if db.benutzer_by_username(settings.database_path, anfrage.username):
        raise HTTPException(400, f"Benutzer '{anfrage.username}' existiert bereits.")
    benutzer_id = db.benutzer_anlegen(
        settings.database_path, anfrage.username,
        passwort_hashen(anfrage.password), ist_admin=anfrage.ist_admin,
    )
    # Legt den Projektordner direkt an, damit er beim ersten Login nicht
    # fehlt (gleiche Funktion, die auch zur Laufzeit jeden Projekt-Pfad
    # dieses Benutzers aufloest - siehe scripts/benutzer_anlegen.py).
    projekte_wurzel(settings, anfrage.username)
    zeile = db.benutzer_by_id(settings.database_path, benutzer_id)
    return BenutzerEintrag(**{k: zeile[k] for k in ("id", "username", "ist_admin", "created_at")})


@router.delete("/{benutzer_id}", status_code=204)
def loeschen(benutzer_id: int, settings: Settings = Depends(get_settings),
             aktueller_admin: Benutzer = Depends(get_current_user)):
    ziel = db.benutzer_by_id(settings.database_path, benutzer_id)
    if ziel is None:
        raise HTTPException(404, "Benutzer nicht gefunden.")
    if ziel["id"] == aktueller_admin.id:
        raise HTTPException(400, "Der eigene Account kann nicht gelöscht werden.")
    if ziel["ist_admin"]:
        andere_admins = [
            b for b in db.benutzer_alle_auflisten(settings.database_path)
            if b["ist_admin"] and b["id"] != ziel["id"]
        ]
        if not andere_admins:
            raise HTTPException(400, "Es muss mindestens ein Admin-Benutzer bestehen bleiben.")

    # Bestehende Geschichten/Projekte des geloeschten Benutzers gehen nicht
    # verloren, sondern landen beim Standard-Admin (aktuell: Daniel).
    benutzer_projekte_uebertragen(settings, ziel["username"], settings.default_username)
    db.benutzer_loeschen(settings.database_path, benutzer_id)
