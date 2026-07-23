"""CRUD fuer gespeicherte SSH-Ziele + Verbindungstest."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.config import Settings, get_settings
from app.core import ssh_manager
from app.schemas import (
    SSHTestAnfrage,
    SSHTestAntwort,
    SSHZielAnlegenAnfrage,
    SSHZielAntwort,
)
from app.services import ssh_ziel_aus_db

router = APIRouter(prefix="/api/ssh-targets", tags=["ssh-targets"])


def _geheimnis_aus_anfrage(a: SSHZielAnlegenAnfrage) -> dict:
    if a.auth_method == "password":
        return {"password": a.password}
    if a.auth_method == "private_key":
        return {"private_key_pem": a.private_key_pem, "passphrase": a.private_key_passphrase}
    return {}


def _geheimnis_fuer_neuanlage_pruefen(a: SSHZielAnlegenAnfrage) -> None:
    """Serverseitiges Gegenstueck zur Frontend-Validierung: bei einer
    Neuanlage (anders als beim Update) gibt es keinen bestehenden Datensatz,
    auf den ohne Angabe zurueckgefallen werden koennte."""
    if a.auth_method == "password" and not a.password:
        raise HTTPException(400, "Für Authentifizierung per Passwort muss ein Passwort angegeben werden.")
    if a.auth_method == "private_key" and not a.private_key_pem:
        raise HTTPException(400, "Für Authentifizierung per privatem Schlüssel muss dieser angegeben werden.")


@router.get("", response_model=list[SSHZielAntwort])
def liste(settings: Settings = Depends(get_settings)):
    db.init_db(settings.database_path)
    zeilen = db.ssh_ziele_auflisten(settings.database_path)
    return [SSHZielAntwort(**dict(z)) for z in zeilen]


@router.post("", response_model=SSHZielAntwort, status_code=201)
def anlegen(anfrage: SSHZielAnlegenAnfrage, settings: Settings = Depends(get_settings)):
    _geheimnis_fuer_neuanlage_pruefen(anfrage)
    db.init_db(settings.database_path)
    ziel_id = db.ssh_ziel_anlegen(
        settings.database_path, settings.secret_key_path,
        name=anfrage.name, host=anfrage.host, port=anfrage.port,
        username=anfrage.username, auth_method=anfrage.auth_method,
        geheimnis=_geheimnis_aus_anfrage(anfrage),
        remote_ollama_port=anfrage.remote_ollama_port,
    )
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    return SSHZielAntwort(**{k: row[k] for k in row.keys() if k != "secret_encrypted"})


@router.put("/{ziel_id}", response_model=SSHZielAntwort)
def aktualisieren(ziel_id: str, anfrage: SSHZielAnlegenAnfrage,
                   settings: Settings = Depends(get_settings)):
    bestehend = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    if bestehend is None:
        raise HTTPException(404, "SSH-Ziel nicht gefunden.")

    hat_neues_geheimnis = bool(anfrage.password or anfrage.private_key_pem)
    auth_method_geaendert = anfrage.auth_method != bestehend["auth_method"]

    if hat_neues_geheimnis or anfrage.auth_method == "agent":
        geheimnis = _geheimnis_aus_anfrage(anfrage)
    elif auth_method_geaendert:
        # Ohne neue Zugangsdaten bliebe das alte, zur neuen Auth-Methode nicht
        # mehr passende Geheimnis gespeichert (z.B. Passwort in der DB, aber
        # auth_method jetzt 'private_key') - das wuerde bei der naechsten
        # Verbindung mit einer irrefuehrenden Fehlermeldung fehlschlagen.
        raise HTTPException(
            400, "Beim Wechsel der Authentifizierungsart bitte die neuen "
                 "Zugangsdaten (Passwort bzw. privater Schluessel) angeben."
        )
    else:
        geheimnis = None

    db.ssh_ziel_aktualisieren(
        settings.database_path, settings.secret_key_path, ziel_id,
        name=anfrage.name, host=anfrage.host, port=anfrage.port,
        username=anfrage.username, auth_method=anfrage.auth_method,
        geheimnis=geheimnis, remote_ollama_port=anfrage.remote_ollama_port,
    )
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    return SSHZielAntwort(**{k: row[k] for k in row.keys() if k != "secret_encrypted"})


@router.delete("/{ziel_id}", status_code=204)
def loeschen(ziel_id: str, settings: Settings = Depends(get_settings)):
    db.ssh_ziel_loeschen(settings.database_path, ziel_id)


@router.post("/{ziel_id}/test", response_model=SSHTestAntwort)
def verbindung_testen(ziel_id: str, settings: Settings = Depends(get_settings)):
    ziel = ssh_ziel_aus_db(settings, ziel_id)
    erfolgreich, meldung = ssh_manager.verbindung_testen(ziel)
    return SSHTestAntwort(erfolgreich=erfolgreich, meldung=meldung)


@router.post("/test", response_model=SSHTestAntwort)
def verbindung_testen_ungespeichert(anfrage: SSHTestAnfrage):
    """Testet Zugangsdaten, BEVOR sie gespeichert werden - fuer den 'Testen'-
    Knopf im Anlegen-Dialog."""
    ziel = ssh_manager.SSHZiel(
        host=anfrage.host, port=anfrage.port, username=anfrage.username,
        auth_method=anfrage.auth_method, password=anfrage.password,
        private_key_pem=anfrage.private_key_pem,
        private_key_passphrase=anfrage.private_key_passphrase,
        remote_ollama_port=anfrage.remote_ollama_port,
    )
    erfolgreich, meldung = ssh_manager.verbindung_testen(ziel)
    return SSHTestAntwort(erfolgreich=erfolgreich, meldung=meldung)
