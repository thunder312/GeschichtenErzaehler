"""Projekt-Abgleich zwischen zwei Instanzen (Prod <-> lokaler PC), Logik und
Begriffe siehe app/core/projekt_sync.py.

Zwei Rollen in EINEM Router:
- "Server"-Endpunkte (auf jeder Instanz verfuegbar): Projektliste mit Hashes,
  Archiv holen, Archiv einspielen. Sie sind die Gegenstelle fuer die andere
  Instanz und nutzen deren normales Login (Session-Cookie).
- "Client"-Endpunkte (nur sinnvoll, wenn eine Gegenstelle eingetragen ist,
  typisch am lokalen PC): vergleichen, hochladen, herunterladen, lokal
  aufraeumen. Die Gegenstelle kann den PC nicht erreichen (NAT), deshalb
  laeuft jede Uebertragung vom PC aus.

Der Projektordner steckt als Query-Parameter in der URL, nicht im Pfad:
ein `{ordner:path}`-Pfad unter /api/projects wuerde vom projects-Router
verschluckt (siehe fallback_router in app/api/projects.py).
"""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app import db
from app.auth import get_current_user
from app.config import Settings, get_settings
from app.core import geruest as g
from app.core import projekt_dateien as pd
from app.core import projekt_sync as ps
from app.core.geruest import ordnername_aus_titel
from app.schemas import Benutzer
from app.services import projekt_pfad, projekte_wurzel

router = APIRouter(prefix="/api/sync", tags=["sync"])

SICHERUNGS_ORDNER = "_sync_sicherung"
_TIMEOUT = 120


# --- gemeinsame Helfer ------------------------------------------------------

def _projekt_ordner(wurzel: Path) -> list[Path]:
    """Alle Projektordner unter der Wurzel (direkt oder eine Ebene tiefer,
    siehe 'Unterordner je Epoche')."""
    def ist_projekt(p: Path) -> bool:
        return p.is_dir() and (p / "projekt").is_dir()

    ergebnis: list[Path] = []
    for eintrag in sorted(wurzel.iterdir()):
        if not eintrag.is_dir() or eintrag.name == SICHERUNGS_ORDNER:
            continue
        if ist_projekt(eintrag):
            ergebnis.append(eintrag)
            continue
        ergebnis.extend(u for u in sorted(eintrag.iterdir()) if ist_projekt(u))
    return ergebnis


def _info_zu(pfad: Path, wurzel: Path) -> dict:
    projekt = pfad / "projekt"
    geruest_text = pd.lies(pd.geruest_datei(projekt), pflicht=False, ersatz="")
    return ps.info(
        pfad,
        ordner=pfad.relative_to(wurzel).as_posix(),
        titel=g.titel_erkennen(geruest_text) if geruest_text else None,
        epoche=pd.epoche_von_projekt(pfad),
        anzahl_kapitel=len(pd.vorhandene_kapitel(projekt)),
    )


def _lokale_infos(settings: Settings, benutzer: Benutzer) -> list[dict]:
    wurzel = projekte_wurzel(settings, benutzer.username)
    return [_info_zu(p, wurzel) for p in _projekt_ordner(wurzel)]


def _neuer_zielpfad(settings: Settings, username: str, epoche: str | None, name: str) -> Path:
    wurzel = projekte_wurzel(settings, username)
    if epoche and db.einstellung_unterordner_je_epoche_lesen(settings.database_path):
        wurzel = wurzel / ordnername_aus_titel(epoche)
    name = ordnername_aus_titel(name)
    ziel, zaehler = wurzel / name, 2
    while ziel.exists():
        ziel = wurzel / f"{name}-{zaehler}"
        zaehler += 1
    return ziel


# --- Server-Seite: Gegenstelle fuer die andere Instanz -----------------------

@router.get("/projekte")
def projekte_mit_hash(settings: Settings = Depends(get_settings),
                      benutzer: Benutzer = Depends(get_current_user)):
    return _lokale_infos(settings, benutzer)


@router.get("/archiv")
def archiv_holen(ordner: str = Query(...), settings: Settings = Depends(get_settings),
                 benutzer: Benutzer = Depends(get_current_user)):
    pfad = projekt_pfad(settings, benutzer.username, ordner)
    laufend = ps.laufende_jobs(pfad)
    if laufend:
        raise HTTPException(409, f"Im Projekt läuft noch ein Job ({', '.join(laufend)}).")
    return Response(content=ps.archiv_erzeugen(pfad), media_type="application/gzip")


@router.post("/archiv")
async def archiv_einspielen(request: Request,
                            projekt_id: str = Query(...),
                            epoche: str | None = Query(None),
                            name: str = Query(...),
                            quell_hash: str = Query(...),
                            ziel_ordner: str | None = Query(None),
                            erwarteter_hash: str | None = Query(None),
                            settings: Settings = Depends(get_settings),
                            benutzer: Benutzer = Depends(get_current_user)):
    daten = await request.body()
    wurzel = projekte_wurzel(settings, benutzer.username)

    ziel: Path | None = None
    if ziel_ordner:
        ziel = projekt_pfad(settings, benutzer.username, ziel_ordner)
    else:
        for p in _projekt_ordner(wurzel):
            if ps.meta_lesen(p).get("projekt_id") == projekt_id:
                ziel = p
                break

    if ziel is not None:
        laufend = ps.laufende_jobs(ziel)
        if laufend:
            raise HTTPException(409, f"Auf der Zielseite läuft noch ein Job ({', '.join(laufend)}).")
        if erwarteter_hash is not None and ps.inhalt_hash(ziel) != erwarteter_hash:
            raise HTTPException(409, "Das Projekt auf der Zielseite wurde zwischenzeitlich geändert. "
                                     "Bitte den Vergleich neu laden.")
        ps.sicherung_anlegen(ziel, wurzel / SICHERUNGS_ORDNER)
    else:
        ziel = _neuer_zielpfad(settings, benutzer.username, epoche, name)

    try:
        ps.archiv_entpacken(daten, ziel)
    except (ValueError, OSError, EOFError) as e:
        raise HTTPException(400, f"Archiv unbrauchbar: {e}") from e

    neuer_hash = ps.inhalt_hash(ziel)
    if neuer_hash != quell_hash:
        raise HTTPException(500, "Prüfsumme nach dem Entpacken stimmt nicht – Übertragung fehlerhaft. "
                                 "Die vorherige Fassung liegt im Sicherungsordner.")
    ps.abgleich_vermerken(ziel, id_=projekt_id, hash_=neuer_hash, richtung="eingespielt", partner="gegenstelle")
    return {"ordner": ziel.relative_to(wurzel).as_posix(), "hash": neuer_hash}


@router.get("/projekt-status")
def projekt_status(ordner: str = Query(...), settings: Settings = Depends(get_settings),
                   benutzer: Benutzer = Depends(get_current_user)):
    """Fuer den 'Pruefung abschliessen'-Dialog: Gibt es eine Gegenstelle, und
    wurde dieses Projekt schon einmal mit ihr abgeglichen (= es existiert
    vermutlich noch eine Kopie dort)?"""
    pfad = projekt_pfad(settings, benutzer.username, ordner)
    meta = ps.meta_lesen(pfad)
    return {
        "partner_konfiguriert": db.sync_partner_lesen(settings.database_path, settings.secret_key_path) is not None,
        "abgeglichen": bool(meta.get("basis_hash")),
    }


class AufraeumenVormerkenAnfrage(BaseModel):
    ordner: str
    vormerken: bool = True


@router.post("/aufraeumen-vormerken")
def aufraeumen_vormerken(anfrage: AufraeumenVormerkenAnfrage, settings: Settings = Depends(get_settings),
                         benutzer: Benutzer = Depends(get_current_user)):
    """Merkt vor, dass die Kopie auf dem PC nach abgeschlossener Pruefung
    entfernt werden darf (der PC holt sich das beim naechsten Vergleich ab)."""
    pfad = projekt_pfad(settings, benutzer.username, anfrage.ordner)
    meta = ps.meta_lesen(pfad)
    meta["projekt_id"] = ps.projekt_id(pfad)
    if anfrage.vormerken:
        meta["lokal_aufraeumen"] = True
    else:
        meta.pop("lokal_aufraeumen", None)
    ps.meta_schreiben(pfad, meta)
    return {"vorgemerkt": anfrage.vormerken}


# --- Client-Seite: Gegenstelle ansprechen -----------------------------------

class PartnerAnfrage(BaseModel):
    url: str
    username: str
    # None = gespeichertes Passwort beibehalten
    password: str | None = None


def _partner_oder_fehler(settings: Settings) -> dict:
    partner = db.sync_partner_lesen(settings.database_path, settings.secret_key_path)
    if not partner:
        raise HTTPException(400, "Keine Gegenstelle für den Abgleich eingetragen (Einstellungen).")
    return partner


class _Gegenstelle:
    """Eingeloggte requests-Session gegen die andere Instanz."""

    def __init__(self, partner: dict):
        self.basis = partner["url"].rstrip("/")
        self.s = httpx.Client(timeout=_TIMEOUT)
        try:
            r = self.s.post(f"{self.basis}/api/auth/login",
                            json={"username": partner["username"], "password": partner["password"]},
                            timeout=30)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Gegenstelle nicht erreichbar: {e}") from e
        if r.status_code == 401:
            raise HTTPException(502, "Gegenstelle: Benutzername oder Passwort falsch.")
        if r.is_error:
            raise HTTPException(502, f"Gegenstelle: Anmeldung fehlgeschlagen (HTTP {r.status_code}).")

    def _antwort(self, r: httpx.Response) -> httpx.Response:
        if r.is_success:
            return r
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text[:300]
        raise HTTPException(409 if r.status_code == 409 else 502, f"Gegenstelle: {detail}")

    def get(self, pfad: str, **kw) -> httpx.Response:
        try:
            return self._antwort(self.s.get(f"{self.basis}{pfad}", **kw))
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Gegenstelle nicht erreichbar: {e}") from e

    def post(self, pfad: str, **kw) -> httpx.Response:
        try:
            return self._antwort(self.s.post(f"{self.basis}{pfad}", **kw))
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Gegenstelle nicht erreichbar: {e}") from e


@router.get("/partner")
def partner_lesen(settings: Settings = Depends(get_settings)):
    partner = db.sync_partner_lesen(settings.database_path, settings.secret_key_path)
    if not partner:
        return {"konfiguriert": False, "url": "", "username": "", "passwort_gesetzt": False}
    return {"konfiguriert": True, "url": partner["url"], "username": partner["username"],
            "passwort_gesetzt": bool(partner["password"])}


@router.put("/partner")
def partner_schreiben(anfrage: PartnerAnfrage, settings: Settings = Depends(get_settings),
                      _benutzer: Benutzer = Depends(get_current_user)):
    url = anfrage.url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Die URL muss mit http:// oder https:// beginnen.")
    db.sync_partner_schreiben(settings.database_path, settings.secret_key_path,
                              url=url, username=anfrage.username.strip(), password=anfrage.password)
    return partner_lesen(settings)


@router.delete("/partner", status_code=204)
def partner_loeschen(settings: Settings = Depends(get_settings), _benutzer: Benutzer = Depends(get_current_user)):
    db.sync_partner_loeschen(settings.database_path)


@router.post("/partner/test")
def partner_testen(settings: Settings = Depends(get_settings), _benutzer: Benutzer = Depends(get_current_user)):
    gegenstelle = _Gegenstelle(_partner_oder_fehler(settings))
    anzahl = len(gegenstelle.get("/api/sync/projekte").json())
    return {"ok": True, "projekte": anzahl}


def _zuordnen(lokal: list[dict], server: list[dict]) -> list[tuple[dict | None, dict | None]]:
    """Paart lokale und Server-Projekte: erst per Projekt-ID, dann (fuer von
    Hand kopierte Projekte ohne gemeinsame ID) per eindeutigem Projektnamen."""
    paare: list[tuple[dict | None, dict | None]] = []
    rest_server = list(server)
    rest_lokal: list[dict] = []
    for l in lokal:
        treffer = next((s for s in rest_server if s["projekt_id"] == l["projekt_id"]), None)
        if treffer:
            rest_server.remove(treffer)
            paare.append((l, treffer))
        else:
            rest_lokal.append(l)
    uebrig_lokal: list[dict] = []
    for l in rest_lokal:
        kandidaten = [s for s in rest_server if s["name"] == l["name"]]
        gleichnamig_lokal = [x for x in rest_lokal if x["name"] == l["name"]]
        if len(kandidaten) == 1 and len(gleichnamig_lokal) == 1:
            rest_server.remove(kandidaten[0])
            paare.append((l, kandidaten[0]))
        else:
            uebrig_lokal.append(l)
    paare.extend((l, None) for l in uebrig_lokal)
    paare.extend((None, s) for s in rest_server)
    return paare


def _bewerten(lokal: dict | None, server: dict | None) -> dict:
    vergleich = ps.vergleichen(lokal, server)
    if lokal and server and lokal["projekt_id"] != server["projekt_id"]:
        vergleich["unsicher"] = True  # per Name gepaart, noch nie abgeglichen
    return vergleich


def _darf_lokal_weg(vergleich: dict) -> bool:
    """Lokal entfernen ist verlustfrei, wenn der Server alles hat: identisch,
    oder nur der Server wurde seit dem letzten Abgleich weiterentwickelt."""
    return vergleich["status"] == "gleich" or (vergleich["status"] == "server_neuer" and not vergleich["unsicher"])


@router.get("/vergleich")
def vergleichen(settings: Settings = Depends(get_settings), benutzer: Benutzer = Depends(get_current_user)):
    gegenstelle = _Gegenstelle(_partner_oder_fehler(settings))
    server = gegenstelle.get("/api/sync/projekte").json()
    lokal = _lokale_infos(settings, benutzer)
    zeilen = []
    for l, s in _zuordnen(lokal, server):
        v = _bewerten(l, s)
        zeilen.append({
            "name": (l or s)["name"],
            "titel": (l or s).get("titel"),
            "epoche": (l or s).get("epoche"),
            "lokal": l,
            "server": s,
            "status": v["status"],
            "unsicher": v["unsicher"],
            "nachricht": v["nachricht"],
            "aufraeumen_vorgemerkt": bool(s and s.get("lokal_aufraeumen") and l and _darf_lokal_weg(v)),
        })
    zeilen.sort(key=lambda z: (z["epoche"] or "", z["name"]))
    return {"zeilen": zeilen}


class UebertragenAnfrage(BaseModel):
    # Ordner des Projekts auf der QUELLSEITE (hochladen: lokal, herunterladen: Server)
    ordner: str
    force: bool = False


def _paar_zu(settings: Settings, benutzer: Benutzer, gegenstelle: _Gegenstelle,
             ordner: str, quelle_ist_lokal: bool):
    lokal = _lokale_infos(settings, benutzer)
    server = gegenstelle.get("/api/sync/projekte").json()
    for l, s in _zuordnen(lokal, server):
        if (l if quelle_ist_lokal else s) and (l if quelle_ist_lokal else s)["ordner"] == ordner:
            return l, s
    raise HTTPException(404, f"Projekt '{ordner}' nicht gefunden.")


def _warnung_oder_fehler(vergleich: dict, richtung: str, force: bool) -> None:
    warnung = ps.uebertragung_pruefen(vergleich, richtung)
    if warnung and not force:
        raise HTTPException(409, detail={"art": "ueberschreiben", "status": vergleich["status"],
                                         "nachricht": warnung})


@router.post("/hochladen")
def hochladen(anfrage: UebertragenAnfrage, settings: Settings = Depends(get_settings),
              benutzer: Benutzer = Depends(get_current_user)):
    gegenstelle = _Gegenstelle(_partner_oder_fehler(settings))
    lokal, server = _paar_zu(settings, benutzer, gegenstelle, anfrage.ordner, quelle_ist_lokal=True)
    if lokal["laufende_jobs"]:
        raise HTTPException(409, f"Im lokalen Projekt läuft noch ein Job ({', '.join(lokal['laufende_jobs'])}).")
    vergleich = _bewerten(lokal, server)
    if vergleich["status"] == "gleich":
        return {"uebertragen": False, "nachricht": "Bereits identisch – nichts zu tun."}
    _warnung_oder_fehler(vergleich, "hoch", anfrage.force)

    pfad = projekt_pfad(settings, benutzer.username, anfrage.ordner)
    # Hash NACH dem Laden der Infos erneut pruefen: der Benutzer koennte
    # zwischenzeitlich weitergeschrieben haben.
    aktuell = ps.inhalt_hash(pfad)
    daten = ps.archiv_erzeugen(pfad)
    params = {"projekt_id": lokal["projekt_id"], "name": lokal["name"], "quell_hash": aktuell}
    if lokal["epoche"]:
        params["epoche"] = lokal["epoche"]
    if server:
        params["ziel_ordner"] = server["ordner"]
        params["erwarteter_hash"] = server["hash"]
    antwort = gegenstelle.post("/api/sync/archiv", params=params, content=daten,
                               headers={"Content-Type": "application/gzip"}).json()
    ps.abgleich_vermerken(pfad, id_=lokal["projekt_id"], hash_=antwort["hash"], richtung="hochgeladen",
                          partner=gegenstelle.basis)
    return {"uebertragen": True, "ordner": antwort["ordner"], "nachricht": "Zum Server hochgeladen."}


@router.post("/herunterladen")
def herunterladen(anfrage: UebertragenAnfrage, settings: Settings = Depends(get_settings),
                  benutzer: Benutzer = Depends(get_current_user)):
    gegenstelle = _Gegenstelle(_partner_oder_fehler(settings))
    lokal, server = _paar_zu(settings, benutzer, gegenstelle, anfrage.ordner, quelle_ist_lokal=False)
    if server["laufende_jobs"]:
        raise HTTPException(409, f"Auf dem Server läuft noch ein Job ({', '.join(server['laufende_jobs'])}).")
    vergleich = _bewerten(lokal, server)
    if vergleich["status"] == "gleich":
        return {"uebertragen": False, "nachricht": "Bereits identisch – nichts zu tun."}
    _warnung_oder_fehler(vergleich, "runter", anfrage.force)

    daten = gegenstelle.get("/api/sync/archiv", params={"ordner": server["ordner"]}).content
    wurzel = projekte_wurzel(settings, benutzer.username)
    if lokal:
        ziel = projekt_pfad(settings, benutzer.username, lokal["ordner"])
        if ps.laufende_jobs(ziel):
            raise HTTPException(409, "Im lokalen Projekt läuft noch ein Job.")
        if ps.inhalt_hash(ziel) != lokal["hash"]:
            raise HTTPException(409, "Das lokale Projekt wurde zwischenzeitlich geändert – Vergleich neu laden.")
        ps.sicherung_anlegen(ziel, wurzel / SICHERUNGS_ORDNER)
    else:
        ziel = _neuer_zielpfad(settings, benutzer.username, server["epoche"], server["name"])
    try:
        ps.archiv_entpacken(daten, ziel)
    except (ValueError, OSError, EOFError) as e:
        raise HTTPException(400, f"Archiv unbrauchbar: {e}") from e
    neuer_hash = ps.inhalt_hash(ziel)
    if neuer_hash != server["hash"]:
        raise HTTPException(500, "Prüfsumme nach dem Entpacken stimmt nicht – Übertragung fehlerhaft.")
    ps.abgleich_vermerken(ziel, id_=server["projekt_id"], hash_=neuer_hash, richtung="heruntergeladen",
                          partner=gegenstelle.basis)
    return {"uebertragen": True, "ordner": ziel.relative_to(wurzel).as_posix(),
            "nachricht": "Vom Server geholt."}


class LokalAufraeumenAnfrage(BaseModel):
    ordner: str  # lokaler Ordner
    # True: ist die lokale Fassung neuer, erst hochladen, dann entfernen.
    vorher_hochladen: bool = False


def lokal_entfernen_wenn_synchron(settings: Settings, benutzer: Benutzer, ordner: str,
                                  vorher_hochladen: bool) -> dict:
    """Loescht die lokale Projektkopie (nicht die daneben liegenden PDFs),
    aber NUR, wenn der Server alle lokalen Aenderungen schon hat."""
    gegenstelle = _Gegenstelle(_partner_oder_fehler(settings))
    lokal, server = _paar_zu(settings, benutzer, gegenstelle, ordner, quelle_ist_lokal=True)
    vergleich = _bewerten(lokal, server)
    if vergleich["status"] in ("lokal_neuer", "nur_lokal") and vorher_hochladen:
        hochladen(UebertragenAnfrage(ordner=ordner), settings, benutzer)
        lokal, server = _paar_zu(settings, benutzer, gegenstelle, ordner, quelle_ist_lokal=True)
        vergleich = _bewerten(lokal, server)
    if not _darf_lokal_weg(vergleich):
        raise HTTPException(409, detail={
            "art": "nicht_synchron", "status": vergleich["status"],
            "nachricht": "Lokal entfernt wird nur, wenn der Server alle lokalen Änderungen schon hat. "
                         + vergleich["nachricht"]})
    pfad = projekt_pfad(settings, benutzer.username, ordner)
    behalten = ps.projekt_leeren(pfad)
    # Leeren Epoche-Ordner NICHT entfernen: dort liegen die exportierten PDFs.
    hinweis = f" {behalten} MP3-/Titelbild-Verlaufsdatei(en) bleiben hier liegen." if behalten else ""
    return {"entfernt": True, "nachricht": "Lokale Projektdateien entfernt." + hinweis}


@router.post("/lokal-aufraeumen")
def lokal_aufraeumen(anfrage: LokalAufraeumenAnfrage, settings: Settings = Depends(get_settings),
                     benutzer: Benutzer = Depends(get_current_user)):
    return lokal_entfernen_wenn_synchron(settings, benutzer, anfrage.ordner, anfrage.vorher_hochladen)
