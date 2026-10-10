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

import threading

from fastapi import APIRouter, Depends, HTTPException, Path

from app import db
from app.auth import get_current_admin, get_current_user
from app.config import Settings, get_settings
from app.core import athene_steuerung as ath
from app.core import ki_start, ollama_client, ssh_manager
from app.core.rollen import ROLLEN
from app.schemas import (
    Benutzer,
    HostContainerAktionAntwort,
    HostStatusAntwort,
    KiStartStatus,
    OllamaModellInfo,
    SSHTestAnfrage,
    SSHTestAntwort,
    SSHZielAnlegenAnfrage,
    SSHZielAntwort,
    SSHZielFavoritAnfrage,
)
from app.services import (
    athene_container_setzen,
    athene_docker_starten,
    athene_status,
    athene_steuerung_verfuegbar,
    ollama_basis_url,
    ssh_ziel_aus_db,
)

router = APIRouter(prefix="/api/ssh-targets", tags=["ssh-targets"])


def _geheimnis_aus_anfrage(a: SSHZielAnlegenAnfrage) -> dict:
    if a.auth_method == "password":
        geheim = {"password": a.password}
    elif a.auth_method == "private_key":
        geheim = {"private_key_pem": a.private_key_pem, "passphrase": a.private_key_passphrase}
    else:
        geheim = {}
    # steuer_token gilt fuer alle Auth-Methoden (bei 'direct' der einzige
    # Geheimnis-Bestandteil) - leerer String bedeutet: keinen Token hinterlegen.
    if a.steuer_token and a.steuer_token.strip():
        geheim["steuer_token"] = a.steuer_token.strip()
    return geheim


def _antwort_aus_row(settings: Settings, row) -> SSHZielAntwort:
    felder = {k: row[k] for k in row.keys() if k not in ("secret_encrypted",)}
    geheim = db.ssh_ziel_geheimnis(row, settings.secret_key_path) if "secret_encrypted" in row.keys() else {}
    felder["steuer_token_gesetzt"] = bool(geheim.get("steuer_token"))
    return SSHZielAntwort(**felder)


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
    # Bewusst OHNE get_current_admin: jeder eingeloggte Benutzer braucht
    # diese Liste fuer das KI-Ziel-Dropdown im Kopfbereich (siehe
    # frontend/src/App.tsx) - nur das Anlegen/Aendern/Loeschen/Testen der
    # Ziele selbst (Tab "KI-Ziele") ist Admins vorbehalten.
    db.init_db(settings.database_path)
    zeilen = db.ssh_ziele_auflisten(settings.database_path)
    return [_antwort_aus_row(settings, z) for z in zeilen]


@router.post("", response_model=SSHZielAntwort, status_code=201, dependencies=[Depends(get_current_admin)])
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
        bildki_port=anfrage.bildki_port,
        bildki_port_pony=anfrage.bildki_port_pony,
        steuer_port=anfrage.steuer_port,
    )
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    return _antwort_aus_row(settings, row)


@router.put("/{ziel_id}", response_model=SSHZielAntwort, dependencies=[Depends(get_current_admin)])
def aktualisieren(ziel_id: str, anfrage: SSHZielAnlegenAnfrage,
                   settings: Settings = Depends(get_settings)):
    bestehend = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    if bestehend is None:
        raise HTTPException(404, "KI-Ziel nicht gefunden.")
    _grundstruktur_pruefen(anfrage)

    hat_neues_geheimnis = bool(anfrage.password or anfrage.private_key_pem)
    auth_method_geaendert = anfrage.auth_method != bestehend["auth_method"]
    kein_geheimnis_noetig = anfrage.auth_method in ("agent", "direct")
    # Leeres steuer_token-Feld = unveraendert lassen (analog zu Passwoertern);
    # nur ein neu eingegebener Token ueberschreibt.
    neuer_steuer_token = (anfrage.steuer_token or "").strip()
    bestehendes_geheim = db.ssh_ziel_geheimnis(bestehend, settings.secret_key_path)

    if hat_neues_geheimnis or kein_geheimnis_noetig or neuer_steuer_token:
        geheimnis = _geheimnis_aus_anfrage(anfrage)
        if not neuer_steuer_token and bestehendes_geheim.get("steuer_token"):
            geheimnis["steuer_token"] = bestehendes_geheim["steuer_token"]
    elif auth_method_geaendert:
        # Ohne neue Zugangsdaten bliebe das alte, zur neuen Auth-Methode nicht
        # mehr passende Geheimnis gespeichert (z.B. Passwort in der DB, aber
        # auth_method jetzt 'private_key') - das wuerde bei der naechsten
        # Verbindung mit einer irrefuehrenden Fehlermeldung fehlschlagen.
        raise HTTPException(
            400, "Beim Wechsel der Authentifizierungsart bitte die neuen "
                 "Zugangsdaten (Passwort bzw. privater Schlüssel) angeben."
        )
    else:
        geheimnis = None

    db.ssh_ziel_aktualisieren(
        settings.database_path, settings.secret_key_path, ziel_id,
        name=anfrage.name, host=anfrage.host, port=anfrage.port,
        username=anfrage.username, auth_method=anfrage.auth_method,
        geheimnis=geheimnis, remote_ollama_port=anfrage.remote_ollama_port,
        bildki_port=anfrage.bildki_port,
        bildki_port_pony=anfrage.bildki_port_pony,
        steuer_port=anfrage.steuer_port,
    )
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    return _antwort_aus_row(settings, row)


@router.delete("/{ziel_id}", status_code=204, dependencies=[Depends(get_current_admin)])
def loeschen(ziel_id: str, settings: Settings = Depends(get_settings)):
    db.ssh_ziel_loeschen(settings.database_path, ziel_id)


@router.put("/{ziel_id}/favorit", response_model=SSHZielAntwort, dependencies=[Depends(get_current_admin)])
def favorit_setzen(ziel_id: str, anfrage: SSHZielFavoritAnfrage,
                    settings: Settings = Depends(get_settings)):
    if db.ssh_ziel_lesen(settings.database_path, ziel_id) is None:
        raise HTTPException(404, "KI-Ziel nicht gefunden.")
    db.ssh_ziel_favorit_setzen(settings.database_path, ziel_id, anfrage.favorit)
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    return _antwort_aus_row(settings, row)


@router.post("/{ziel_id}/test", response_model=SSHTestAntwort, dependencies=[Depends(get_current_admin)])
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


@router.get("/{ziel_id}/erreichbar", response_model=SSHTestAntwort)
def erreichbar(ziel_id: str, settings: Settings = Depends(get_settings),
               benutzer: Benutzer = Depends(get_current_user)):
    """Leichtgewichtiger Erreichbarkeits-Check fuer den KI-Ziel-Umschalter im
    Kopfbereich (frontend/src/components/KiZielUmschalter.tsx) - z.B. ob der
    PC laeuft, bevor man darauf einen Lauf startet. Anders als /test fuer
    jeden eingeloggten Nutzer und mit kurzem Timeout bei 'direct'-Zielen.
    Wird nur beim Umschalten/Laden aufgerufen, NICHT gepollt (paralleler
    SSH-Verkehr bremst laufende LLM-Aufrufe ueber denselben Tunnel)."""
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    if row is None:
        raise HTTPException(404, "KI-Ziel nicht gefunden.")
    if row["auth_method"] == "direct":
        try:
            ollama_client.tags_sync(row["host"], timeout=3.0)
            return SSHTestAntwort(erfolgreich=True, meldung="Ollama erreichbar.")
        except Exception as e:
            return SSHTestAntwort(erfolgreich=False, meldung=f"Nicht erreichbar: {e}")
    erfolgreich, meldung = ssh_manager.verbindung_testen(ssh_ziel_aus_db(settings, ziel_id))
    return SSHTestAntwort(erfolgreich=erfolgreich, meldung=meldung)


@router.get("/{ziel_id}/modelle", response_model=list[OllamaModellInfo], dependencies=[Depends(get_current_admin)])
async def modelle_auflisten(ziel_id: str, settings: Settings = Depends(get_settings)):
    """Fragt die auf diesem KI-Ziel tatsaechlich verfuegbaren Ollama-Modelle
    ab (fuer die Persona-Modell-Zuordnung im selben Tab, siehe
    app/api/persona_modelle.py) - nutzt denselben ollama_basis_url()-
    Mechanismus wie die eigentlichen Pipeline-Aufrufe, oeffnet also bei
    einem SSH-Ziel kurz einen Tunnel. ollama_basis_url() wirft bereits eine
    HTTPException(404), falls ziel_id unbekannt ist."""
    with ollama_basis_url(settings, ziel_id) as base_url:
        try:
            daten = await ollama_client.tags(base_url)
        except Exception as e:
            raise HTTPException(502, f"KI-Ziel nicht erreichbar: {e}") from e
    return [
        OllamaModellInfo(
            name=m["name"],
            parameter_size=m.get("details", {}).get("parameter_size"),
            size_bytes=m.get("size"),
        )
        for m in daten.get("models", [])
    ]


@router.get("/{ziel_id}/host-status", response_model=HostStatusAntwort)
def host_status(ziel_id: str, settings: Settings = Depends(get_settings),
                benutzer: Benutzer = Depends(get_current_user)):
    """Speicher-/Container-Lage des KI-Hosts (Feature "KI- und
    Speicherkontrolle", siehe app/core/athene_steuerung.py). Bewusst fuer
    jeden eingeloggten Nutzer erreichbar - der Schreibstart-Ablauf braucht
    das. Liefert `verfuegbar: false` (statt eines Fehlers), wenn dieses
    KI-Ziel keinen Steuer-Weg hat, damit das Frontend das Feature dann
    einfach ausblendet."""
    sk_aktiv, container = db.einstellung_speicherkontrolle_lesen(settings.database_path)
    try:
        d = athene_status(settings, ziel_id, container)
    except ath.SteuerFehler:
        return HostStatusAntwort(verfuegbar=False)
    # herunterfahren_empfohlen ist zugleich das Signal fuers Frontend, ob der
    # Schreibstart-Dialog erscheinen soll - deshalb hier auch an die
    # Feature-Einstellung koppeln, nicht nur an die Speicherlage.
    d["herunterfahren_empfohlen"] = sk_aktiv and ath.herunterfahren_empfohlen(d)
    return HostStatusAntwort(**d)


@router.post("/{ziel_id}/container/{name}/{aktion}", response_model=HostContainerAktionAntwort)
def host_container(ziel_id: str, name: str,
                   aktion: str = Path(pattern="^(start|stop)$"),
                   settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    """Startet/stoppt EINEN Container auf dem KI-Host. Nur Container aus der
    Einstellung `speicherkontrolle_container` sind erlaubt (der Steuer-Dienst
    auf dem Host hat zusaetzlich seine eigene Whitelist)."""
    _, erlaubt = db.einstellung_speicherkontrolle_lesen(settings.database_path)
    if name not in erlaubt:
        raise HTTPException(403, f"Container '{name}' ist nicht für die Fernsteuerung freigegeben.")
    try:
        return HostContainerAktionAntwort(**athene_container_setzen(settings, ziel_id, name, aktion))
    except ath.SteuerFehler as e:
        raise HTTPException(502, str(e)) from e


# ---------------------------------------------------------------------------
# "KI starten & Modelle scannen" - Hintergrund-Job je KI-Ziel
# ---------------------------------------------------------------------------
# Der Docker-Start kann laenger dauern als ein Proxy-Timeout; deshalb laeuft der
# Ablauf im Hintergrund, das Frontend fragt den Fortschritt ab. Nur im Speicher:
# nach einem Backend-Neustart ist ein laufender Job weg, der Knopf startet neu.
_ki_start_jobs: dict[str, KiStartStatus] = {}
_ki_start_sperre = threading.Lock()


def _modelle_aus_tags(daten: dict) -> list[dict]:
    return [
        {"name": m["name"], "parameter_size": m.get("details", {}).get("parameter_size"),
         "size_bytes": m.get("size")}
        for m in daten.get("models", [])
    ]


def _erwartete_modelle(settings: Settings, ziel_id: str) -> list[str]:
    """Modelle, die die Personas auf diesem Ziel brauchen (Override oder Default)."""
    overrides = db.persona_modelle_alle_lesen(settings.database_path, ziel_id)
    return sorted({overrides.get(p) or cfg["modell"] for p, cfg in ROLLEN.items()})


def _ki_start_lauf(settings: Settings, ziel_id: str) -> None:
    status = _ki_start_jobs[ziel_id]

    def schritt(text: str) -> None:
        status.schritte.append(text)

    try:
        with ollama_basis_url(settings, ziel_id) as base_url:
            steuerbar = athene_steuerung_verfuegbar(settings, ziel_id)
            hilfen = ki_start.KiStartHilfen(
                modelle_lesen=lambda: _modelle_aus_tags(ollama_client.tags_sync(base_url, timeout=4.0)),
                steuer_status=(lambda: athene_status(settings, ziel_id, [ki_start.OLLAMA_CONTAINER]))
                if steuerbar else None,
                docker_starten=lambda: athene_docker_starten(settings, ziel_id),
                container_starten=(lambda name: athene_container_setzen(settings, ziel_id, name, "start"))
                if steuerbar else None,
                erwartete_modelle=lambda: _erwartete_modelle(settings, ziel_id),
            )
            erg = ki_start.ki_starten(hilfen, schritt)
        status.erfolgreich = erg.erfolgreich
        status.fehler = erg.fehler
        status.modelle = [OllamaModellInfo(**m) for m in erg.modelle]
        status.fehlende_modelle = erg.fehlende_modelle
    except HTTPException as e:
        status.erfolgreich, status.fehler = False, str(e.detail)
        status.schritte.append(str(e.detail))
    except Exception as e:  # noqa: BLE001 - Job darf nie ohne Abschluss enden
        status.erfolgreich, status.fehler = False, f"Unerwarteter Fehler: {e}"
        status.schritte.append(status.fehler)
    finally:
        status.laeuft, status.fertig = False, True


@router.post("/{ziel_id}/ki-starten", response_model=KiStartStatus)
def ki_starten(ziel_id: str, settings: Settings = Depends(get_settings),
               benutzer: Benutzer = Depends(get_current_user)):
    """Startet "KI starten & Modelle scannen" fuer dieses Ziel im Hintergrund
    (laeuft schon einer, wird dessen Stand zurueckgegeben)."""
    if db.ssh_ziel_lesen(settings.database_path, ziel_id) is None:
        raise HTTPException(404, "KI-Ziel nicht gefunden.")
    with _ki_start_sperre:
        bisher = _ki_start_jobs.get(ziel_id)
        if bisher is not None and bisher.laeuft:
            return bisher
        _ki_start_jobs[ziel_id] = KiStartStatus(laeuft=True)
        threading.Thread(target=_ki_start_lauf, args=(settings, ziel_id), daemon=True).start()
        return _ki_start_jobs[ziel_id]


@router.get("/{ziel_id}/ki-starten", response_model=KiStartStatus)
def ki_starten_status(ziel_id: str, benutzer: Benutzer = Depends(get_current_user)):
    return _ki_start_jobs.get(ziel_id, KiStartStatus())


@router.post("/test", response_model=SSHTestAntwort, dependencies=[Depends(get_current_admin)])
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
