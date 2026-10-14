"""Abgleich von Projekten zwischen zwei Instanzen (Prod/Strato <-> lokaler PC).

Jedes Projekt bekommt beim ersten Abgleich eine stabile ID (`.sync.json` im
Projektordner, wird NICHT mitubertragen, sondern pro Instanz gefuehrt). Zur
Frage "welche Seite ist neuer?" dient ein Inhalts-Hash ueber alle
inhaltlichen Projektdateien plus der "Basis-Hash" - der Hash, den BEIDE Seiten
nach dem letzten Abgleich hatten. Daraus folgt (Dreiwege-Vergleich):

- nur lokal geaendert  -> "lokal_neuer"   (Hochladen unkritisch)
- nur Server geaendert -> "server_neuer"  (Herunterladen unkritisch)
- beide geaendert      -> "abweichend"    (ein Ueberschreiben verliert Arbeit)

Fehlt eine gemeinsame Basis (z.B. Projekt wurde von Hand kopiert), entscheidet
ersatzweise der Zeitstempel der juengsten Aenderung ("unsicher"). Ein spaeteres
Zusammenfuehren (Merge) zweier abweichender Staende ist bewusst NICHT Teil
dieses Moduls.
"""
from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import tarfile
import time
import uuid
from datetime import datetime
from pathlib import Path

SYNC_DATEI = ".sync.json"

# Nie uebertragen und nie gehasht: instanz-lokale Metadaten, Sicherungen und
# Dateisystem-Muell (Dropbox/Windows).
_TRANSFER_AUSSCHLUSS = ("*.bak", SYNC_DATEI, "desktop.ini", "Thumbs.db", ".dropbox*", "*.tmp", "__pycache__")
# Werden uebertragen (z.B. damit "Fortsetzen" nach dem Umzug klappt), zaehlen
# aber nicht fuer den Hash: Laufzeit-Status aendert sich staendig (Zeitstempel,
# Log-Zeilen), ohne dass sich am Projektinhalt etwas geaendert haette.
_HASH_AUSSCHLUSS = ("*_status.json", "status.json")


def _passt(rel: Path, muster: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(teil, m) for teil in rel.parts for m in muster)


def dateien(projekt: Path, *, fuer_hash: bool = False):
    """Alle uebertragbaren Dateien als (relativer POSIX-Pfad, absoluter Pfad),
    stabil sortiert."""
    ergebnis = []
    for pfad in projekt.rglob("*"):
        if not pfad.is_file():
            continue
        rel = pfad.relative_to(projekt)
        if _passt(rel, _TRANSFER_AUSSCHLUSS):
            continue
        if fuer_hash and _passt(rel, _HASH_AUSSCHLUSS):
            continue
        ergebnis.append((rel.as_posix(), pfad))
    ergebnis.sort(key=lambda e: e[0])
    return ergebnis


def inhalt_hash(projekt: Path) -> str:
    gesamt = hashlib.sha256()
    for rel, pfad in dateien(projekt, fuer_hash=True):
        gesamt.update(rel.encode("utf-8") + b"\0")
        gesamt.update(hashlib.sha256(pfad.read_bytes()).digest())
    return gesamt.hexdigest()


def letzte_aenderung(projekt: Path) -> float:
    """Juengster mtime (Sekunden) aller gehashten Dateien - Ersatzkriterium,
    wenn keine gemeinsame Abgleichs-Basis existiert."""
    zeiten = [p.stat().st_mtime for _rel, p in dateien(projekt, fuer_hash=True)]
    return max(zeiten) if zeiten else projekt.stat().st_mtime


def meta_lesen(projekt: Path) -> dict:
    pfad = projekt / SYNC_DATEI
    if not pfad.exists():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return daten if isinstance(daten, dict) else {}


def meta_schreiben(projekt: Path, meta: dict) -> None:
    (projekt / SYNC_DATEI).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def projekt_id(projekt: Path) -> str:
    """Stabile Projekt-ID; wird beim ersten Zugriff vergeben."""
    meta = meta_lesen(projekt)
    if not meta.get("projekt_id"):
        meta["projekt_id"] = uuid.uuid4().hex
        meta_schreiben(projekt, meta)
    return meta["projekt_id"]


def abgleich_vermerken(projekt: Path, *, id_: str, hash_: str, richtung: str, partner: str) -> None:
    """Haelt fest, welcher Stand zuletzt auf beiden Seiten identisch war."""
    meta = meta_lesen(projekt)
    meta.update({
        "projekt_id": id_,
        "basis_hash": hash_,
        "letzter_abgleich": datetime.now().isoformat(timespec="seconds"),
        "letzte_richtung": richtung,
        "partner": partner,
    })
    meta.pop("lokal_aufraeumen", None)
    meta_schreiben(projekt, meta)


def laufende_jobs(projekt: Path) -> list[str]:
    """Namen der Status-Dateien, die einen aktiven Hintergrundjob melden."""
    aktiv = []
    for pfad in projekt.rglob("*status.json"):
        try:
            if json.loads(pfad.read_text(encoding="utf-8")).get("laeuft"):
                aktiv.append(pfad.name)
        except (OSError, ValueError, AttributeError):
            continue
    return aktiv


def info(projekt: Path, *, ordner: str, titel: str | None, epoche: str | None, anzahl_kapitel: int) -> dict:
    meta = meta_lesen(projekt)
    return {
        "projekt_id": projekt_id(projekt),
        "ordner": ordner,
        "name": projekt.name,
        "titel": titel,
        "epoche": epoche,
        "anzahl_kapitel": anzahl_kapitel,
        "hash": inhalt_hash(projekt),
        "basis_hash": meta.get("basis_hash"),
        "letzter_abgleich": meta.get("letzter_abgleich"),
        "geaendert_ts": letzte_aenderung(projekt),
        "lokal_aufraeumen": bool(meta.get("lokal_aufraeumen")),
        "laufende_jobs": laufende_jobs(projekt),
    }


STATUS_TEXTE = {
    "nur_lokal": "Nur auf diesem PC vorhanden.",
    "nur_server": "Nur auf dem Server vorhanden.",
    "gleich": "Beide Seiten sind identisch.",
    "lokal_neuer": "Die lokale Version ist neuer.",
    "server_neuer": "Die Server-Version ist neuer.",
    "abweichend": "Beide Seiten wurden seit dem letzten Abgleich geändert.",
}


def vergleichen(lokal: dict | None, server: dict | None) -> dict:
    """Dreiwege-Vergleich zweier Projekt-Infos (siehe info()). Liefert
    {"status", "unsicher", "nachricht"}."""
    if lokal is None and server is None:
        raise ValueError("Mindestens eine Seite muss vorhanden sein.")
    if server is None:
        return {"status": "nur_lokal", "unsicher": False, "nachricht": STATUS_TEXTE["nur_lokal"]}
    if lokal is None:
        return {"status": "nur_server", "unsicher": False, "nachricht": STATUS_TEXTE["nur_server"]}
    if lokal["hash"] == server["hash"]:
        return {"status": "gleich", "unsicher": False, "nachricht": STATUS_TEXTE["gleich"]}

    gemeinsame_basis = lokal.get("basis_hash") is not None and lokal.get("basis_hash") == server.get("basis_hash")
    if gemeinsame_basis:
        lokal_geaendert = lokal["hash"] != lokal["basis_hash"]
        server_geaendert = server["hash"] != server["basis_hash"]
        if lokal_geaendert and not server_geaendert:
            status = "lokal_neuer"
        elif server_geaendert and not lokal_geaendert:
            status = "server_neuer"
        else:
            status = "abweichend"
        return {"status": status, "unsicher": False, "nachricht": STATUS_TEXTE[status]}

    # Keine gemeinsame Basis: nur der Zeitstempel kann entscheiden.
    differenz = lokal["geaendert_ts"] - server["geaendert_ts"]
    if abs(differenz) < 2:
        status = "abweichend"
    else:
        status = "lokal_neuer" if differenz > 0 else "server_neuer"
    return {
        "status": status,
        "unsicher": True,
        "nachricht": STATUS_TEXTE[status]
        + " (Kein gemeinsamer Abgleichsstand bekannt - nur anhand der Änderungszeit geschätzt.)",
    }


def uebertragung_pruefen(status: dict, richtung: str) -> str | None:
    """None, wenn die Uebertragung ohne Rueckfrage erlaubt ist; sonst die
    Warnung, die der Benutzer ausdruecklich bestaetigen muss. richtung:
    "hoch" (lokal -> Server) oder "runter" (Server -> lokal)."""
    s = status["status"]
    if s == "abweichend":
        return ("Beide Seiten wurden seit dem letzten Abgleich geändert. Beim Überschreiben gehen die "
                "Änderungen der Zielseite verloren (eine Sicherung wird angelegt).")
    if richtung == "hoch" and s == "server_neuer":
        return "Die Version auf dem Server ist NEUER als die lokale. Sie würde durch die ältere überschrieben."
    if richtung == "runter" and s == "lokal_neuer":
        return "Die lokale Version ist NEUER als die auf dem Server. Sie würde durch die ältere überschrieben."
    return None


# --- Archiv -----------------------------------------------------------------

def archiv_erzeugen(projekt: Path) -> bytes:
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as tar:
        for rel, pfad in dateien(projekt):
            tar.add(pfad, arcname=rel, recursive=False)
    return puffer.getvalue()


def _mitglied_pruefen(m: tarfile.TarInfo) -> Path:
    if not (m.isfile() or m.isdir()):
        raise ValueError(f"Unzulässiger Archiv-Eintrag: {m.name}")
    rel = Path(m.name)
    if rel.is_absolute() or ".." in rel.parts or (rel.parts and ":" in rel.parts[0]):
        raise ValueError(f"Unzulässiger Pfad im Archiv: {m.name}")
    return rel


def archiv_entpacken(daten: bytes, ziel: Path) -> None:
    """Spiegelt den Archivinhalt nach `ziel`: Dateien, die im Archiv fehlen
    (und uebertragbar waeren), werden entfernt; instanz-lokale Dateien
    (.sync.json, .bak, ...) bleiben unangetastet."""
    with tarfile.open(fileobj=io.BytesIO(daten), mode="r:gz") as tar:
        mitglieder = tar.getmembers()
        neue = set()
        for m in mitglieder:
            rel = _mitglied_pruefen(m)
            if m.isfile():
                neue.add(rel.as_posix())
        ziel.mkdir(parents=True, exist_ok=True)
        if ziel.exists():
            for rel, pfad in dateien(ziel):
                if rel not in neue:
                    pfad.unlink()
        for m in mitglieder:
            rel = _mitglied_pruefen(m)
            if m.isdir():
                (ziel / rel).mkdir(parents=True, exist_ok=True)
                continue
            ziel_datei = ziel / rel
            ziel_datei.parent.mkdir(parents=True, exist_ok=True)
            quelle = tar.extractfile(m)
            assert quelle is not None
            ziel_datei.write_bytes(quelle.read())
            os.utime(ziel_datei, (m.mtime, m.mtime))
    for unterordner in sorted((p for p in ziel.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        try:
            unterordner.rmdir()  # nur leere Ordner
        except OSError:
            pass


def sicherung_anlegen(projekt: Path, sicherungs_ordner: Path, behalten: int = 3) -> Path:
    """Packt den aktuellen Stand vor einem Ueberschreiben weg."""
    sicherungs_ordner.mkdir(parents=True, exist_ok=True)
    ziel = sicherungs_ordner / f"{projekt.name}_{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    ziel.write_bytes(archiv_erzeugen(projekt))
    alte = sorted(sicherungs_ordner.glob(f"{projekt.name}_*.tar.gz"))
    for alt in alte[:-behalten]:
        alt.unlink()
    return ziel
