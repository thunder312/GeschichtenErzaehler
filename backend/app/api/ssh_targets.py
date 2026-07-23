"""CRUD fuer gespeicherte KI-Ziele + Verbindungstest.

Zwei grundsaetzlich verschiedene Verbindungsarten teilen sich hier bewusst
dieselbe Tabelle/dasselbe Formular statt eigener Endpunkte:
- SSH-Ziele (auth_method 'password'/'private_key'/'agent'): Ollama laeuft
  auf einem entfernten Host/Container, erreichbar nur per SSH-Tunnel
  (siehe app/core/ssh_manager.py).
- Direkte Ziele (auth_method 'direct'): kein SSH noetig, z.B. Ollama laeuft
  bereits direkt erreichbar im lokalen Netz oder auf einer anderen
  Windows-Maschine. 'host' enthaelt hier die komplette Basis-URL
  (z.B. 'http://192.168.1.50:11434') statt eines SSH-Hostnamens;
  username/port/remote_ollama_port bleiben unbenutzt.
Beide erscheinen in der GUI als eine gemeinsame Liste "KI-Ziele" und werden
in den Pipeline-Schritten ueber denselben ssh_ziel_id-Parameter ausgewaehlt
(siehe app/services.py:ollama_basis_url)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.config import Settings, get_settings
from app.core import ollama_client, ssh_manager
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


def _grundstruktur_pruefen(a: SSHZielAnlegenAnfrage) -> None:
    """Strukturelle Validierung, die sowohl bei Neuanlage als auch bei
    jedem Update gilt (unabhaengig davon, ob gerade neue Zugangsdaten
    mitgeschickt wurden)."""
    if a.auth_method != "direct" and not a.username.strip():
        raise HTTPException(400, "Für SSH-Ziele muss ein Benutzername angegeben werden.")
    if a.auth_method == "direct" and not a.host.startswith(("http://", "https://")):
        raise HTTPException(400, "Für ein direktes Ziel muss die Basis-URL mit http:// oder https:// beginnen.")


def _geheimnis_fuer_neuanlage_pruefen(a: SSHZielAnlegenAnfrage) -> None:
    """Nur bei Neuanlage relevant: es gibt keinen bestehenden Datensatz, auf
    dessen Geheimnis ohne Angabe zurueckgefallen werden koennte (bei einem
    Update ist ein leeres Passwort/Schluesselfeld dagegen legitim - siehe
    aktualisieren())."""
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
    _grundstruktur_pruefen(anfrage)
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
        raise HTTPException(404, "KI-Ziel nicht gefunden.")
    _grundstruktur_pruefen(anfrage)

    hat_neues_geheimnis = bool(anfrage.password or anfrage.private_key_pem)
    auth_method_geaendert = anfrage.auth_method != bestehend["auth_method"]
    kein_geheimnis_noetig = anfrage.auth_method in ("agent", "direct")

    if hat_neues_geheimnis or kein_geheimnis_noetig:
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
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    if row is None:
        raise HTTPException(404, "KI-Ziel nicht gefunden.")
    if row["auth_method"] == "direct":
        try:
            ollama_client.tags_sync(row["host"])
            return SSHTestAntwort(erfolgreich=True, meldung="Ollama unter dieser Adresse erreichbar.")
        except Exception as e:
            return SSHTestAntwort(erfolgreich=False, meldung=f"Nicht erreichbar: {e}")

    ziel = ssh_ziel_aus_db(settings, ziel_id)
    erfolgreich, meldung = ssh_manager.verbindung_testen(ziel)
    return SSHTestAntwort(erfolgreich=erfolgreich, meldung=meldung)


@router.post("/test", response_model=SSHTestAntwort)
def verbindung_testen_ungespeichert(anfrage: SSHTestAnfrage):
    """Testet Zugangsdaten, BEVOR sie gespeichert werden - fuer den 'Testen'-
    Knopf im Anlegen-Dialog."""
    if anfrage.auth_method == "direct":
        try:
            ollama_client.tags_sync(anfrage.host)
            return SSHTestAntwort(erfolgreich=True, meldung="Ollama unter dieser Adresse erreichbar.")
        except Exception as e:
            return SSHTestAntwort(erfolgreich=False, meldung=f"Nicht erreichbar: {e}")

    ziel = ssh_manager.SSHZiel(
        host=anfrage.host, port=anfrage.port, username=anfrage.username,
        auth_method=anfrage.auth_method, password=anfrage.password,
        private_key_pem=anfrage.private_key_pem,
        private_key_passphrase=anfrage.private_key_passphrase,
        remote_ollama_port=anfrage.remote_ollama_port,
    )
    erfolgreich, meldung = ssh_manager.verbindung_testen(ziel)
    return SSHTestAntwort(erfolgreich=erfolgreich, meldung=meldung)
