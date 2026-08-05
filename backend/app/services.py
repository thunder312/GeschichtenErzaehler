"""Gemeinsame Hilfsfunktionen, die von mehreren API-Routern gebraucht werden:
Projektordner-Aufloesung und die Entscheidung, ob Ollama lokal oder ueber
einen SSH-Tunnel angesprochen wird.
"""
from __future__ import annotations

import dataclasses
import shutil
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from app import db
from app.config import Settings
from app.core import ssh_manager
from app.core.geruest import ordnername_aus_titel


def projekte_wurzel_unskopiert(settings: Settings) -> Path:
    """Speicherort-Wurzel OHNE Username-Unterordner. Ohne in der DB
    gesetzten Override (siehe app/api/einstellungen.py) gilt
    Settings.projects_dir (Umgebungsvariable/Default) - mit Override der
    dort hinterlegte Pfad, damit der Speicherort ueber die GUI aenderbar
    ist, ohne das Backend neu zu starten. Nur fuer projekte_wurzel() selbst
    und app/migration.py gedacht - alle anderen Aufrufer wollen die pro
    Benutzer verschachtelte Wurzel, siehe projekte_wurzel()."""
    override = db.einstellung_projects_dir_lesen(settings.database_path)
    pfad = Path(override) if override else settings.projects_dir
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def projekte_wurzel(settings: Settings, username: str) -> Path:
    """Wurzelverzeichnis der Story-Projekte EINES Benutzers - ein
    Unterordner je Username unter der eigentlichen Speicherort-Wurzel, damit
    ein User nur seine eigenen Projekte sieht (siehe ToDo.md Deployment).
    Bestehende Projekte aus der Zeit vor dieser Trennung werden einmalig von
    app/migration.py hierher verschoben."""
    wurzel = projekte_wurzel_unskopiert(settings) / ordnername_aus_titel(username)
    wurzel.mkdir(parents=True, exist_ok=True)
    return wurzel


def projekt_pfad(settings: Settings, username: str, ordner: str) -> Path:
    """Verhindert Path-Traversal (z.B. '../../etc') - der Ordnername muss
    ein direkter Unterordner der (benutzerspezifischen) Projekte-Wurzel sein
    und dort auch existieren."""
    wurzel = projekte_wurzel(settings, username).resolve()
    kandidat = (wurzel / ordner).resolve()
    if wurzel not in kandidat.parents and kandidat != wurzel:
        raise HTTPException(400, "Ungültiger Projektordner.")
    if not kandidat.is_dir():
        raise HTTPException(404, f"Projekt '{ordner}' nicht gefunden.")
    return kandidat


def fundus_datei(settings: Settings, username: str) -> Path:
    """Pfad zur Personen-Fundus-Datei EINES Benutzers - liegt direkt unter
    der (benutzerspezifischen) Projekte-Wurzel, unabhaengig von der
    "Unterordner je Epoche"-Einstellung, da der Fundus epochenuebergreifend
    EINE Datei ist (intern nach '## <Epoche>' gegliedert, siehe
    app/core/fundus.py)."""
    return projekte_wurzel(settings, username) / "fundus.md"


def neuer_projekt_pfad(settings: Settings, username: str, titel: str, epoche: str | None = None) -> Path:
    """Ort fuer ein neu anzulegendes Projekt. Ist die Einstellung
    "Unterordner je Epoche" aktiv (siehe app/api/einstellungen.py), landet
    das Projekt in einem nach der Epoche benannten Unterordner der
    (benutzerspezifischen) Speicherort-Wurzel statt direkt darin - erspart
    das manuelle Umstellen des Speicherorts beim Wechsel zwischen Epochen."""
    wurzel = projekte_wurzel(settings, username)
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


def benutzer_projekte_uebertragen(settings: Settings, von_username: str, zu_username: str) -> None:
    """Verschiebt alle Projektordner eines Benutzers zu einem anderen -
    gedacht fuer app/api/benutzer.py: wird ein Benutzer geloescht, sollen
    dessen Geschichten nicht mitgeloescht werden, sondern beim Admin landen
    (siehe ToDo.md). Namenskonflikte werden wie bei neuer_projekt_pfad()
    durch einen angehaengten Zaehler aufgeloest."""
    if von_username == zu_username:
        return
    quelle = projekte_wurzel(settings, von_username)
    ziel = projekte_wurzel(settings, zu_username)
    for eintrag in sorted(quelle.iterdir()):
        ziel_pfad = ziel / eintrag.name
        zaehler = 2
        while ziel_pfad.exists():
            ziel_pfad = ziel / f"{eintrag.name}-{zaehler}"
            zaehler += 1
        shutil.move(str(eintrag), str(ziel_pfad))
    try:
        quelle.rmdir()
    except OSError:
        pass


def ordner_nach_umbenennung(ordner: str, neuer_name: str) -> str:
    """Baut den vollstaendigen relativen Projektordner-Pfad neu zusammen,
    nachdem projektordner_umbenennen() (app/core/projekt_dateien.py) nur
    den eigentlichen Projektordner (letztes Pfadsegment) umbenannt hat.
    Ohne das hier ginge bei aktivem Epoche-Unterordner (z.B.
    "Zukunft/neu" -> "Zukunft/Die-Reise") das Epoche-Praefix verloren -
    der zurueckgegebene neue Ordner waere dann nicht mehr unter der
    Speicherort-Wurzel auffindbar."""
    if "/" in ordner:
        praefix = ordner.rsplit("/", 1)[0]
        return f"{praefix}/{neuer_name}"
    return neuer_name


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


@contextmanager
def bild_basis_url(settings: Settings, ziel_id: str):
    """Liefert eine base_url fuer app/core/bild_generierung.py - Pendant zu
    ollama_basis_url() fuer den sd-server-Container, der auf demselben Host
    wie das gewaehlte Text-KI-Ziel laeuft, aber auf einem eigenen Port
    (bildki_port, siehe app/db.py). Anders als bei Ollama gibt es hier KEIN
    implizites lokales Standardziel - ohne konfigurierten bildki_port ist
    Bildgenerierung fuer dieses KI-Ziel schlicht nicht verfuegbar."""
    row = db.ssh_ziel_lesen(settings.database_path, ziel_id)
    if row is None:
        raise HTTPException(404, "KI-Ziel nicht gefunden.")
    if row["bildki_port"] is None:
        raise HTTPException(
            400, "Für dieses KI-Ziel ist keine Bildgenerierung konfiguriert "
                 "(Bild-Port fehlt, siehe Tab \"KI-Ziele\")."
        )

    if row["auth_method"] == "direct":
        teile = urlsplit(row["host"])
        host_ohne_port = (teile.hostname or teile.netloc.split(":")[0])
        neuer_netloc = f"{host_ohne_port}:{row['bildki_port']}"
        yield urlunsplit((teile.scheme, neuer_netloc, "", "", ""))
        return

    ziel = ssh_ziel_aus_db(settings, ziel_id)
    bild_ziel = dataclasses.replace(ziel, remote_ollama_port=row["bildki_port"])
    try:
        with ssh_manager.tunnel(bild_ziel) as t:
            yield t.base_url
    except ssh_manager.SSHVerbindungsFehler as e:
        raise HTTPException(502, f"SSH-Verbindung fehlgeschlagen: {e}") from e


def rollen_modell_override(settings: Settings, persona: str) -> str | None:
    """Globaler Admin-Override fuer das Modell einer ROLLEN-Persona (siehe
    app/core/rollen.py), gepflegt im Tab "KI-Ziele" -> Persona-Modell-
    Zuordnung. None bedeutet: kein Override gesetzt, es bleibt beim
    Default aus rollen.py. Bewusst hier statt in app/core/ollama_client.py,
    damit core/ ohne DB-Zugriff bleibt (siehe dortiger Kommentar zu
    sammle_antwort())."""
    return db.persona_modell_lesen(settings.database_path, persona)
