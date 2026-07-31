"""Unnuetzes Wissen rund ums Buecherschreiben, das beim Start (siehe
app/main.py) einmalig aus docs/unnützesWissen.csv in die DB geladen wird -
fuer das Zeit-Ueberbrueckungs-Overlay im Frontend waehrend laengerer
KI-Wartezeiten."""
from __future__ import annotations

import random

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.config import Settings, get_settings
from app.schemas import WissenEintrag, WissenNaechstesAntwort

router = APIRouter(prefix="/api/unnuetzeswissen", tags=["wissen"])


@router.get("", response_model=list[WissenEintrag])
def wissen_auflisten(settings: Settings = Depends(get_settings)):
    eintraege = []
    for zeile in db.wissen_alle_lesen(settings.database_path):
        daten = dict(zeile)
        daten["nummer"] = daten.pop("id")
        eintraege.append(WissenEintrag(**daten))
    return eintraege


@router.get("/naechstes", response_model=WissenNaechstesAntwort)
def wissen_naechstes(settings: Settings = Depends(get_settings)):
    """Liefert das naechste Wissen in einer EINMAL gemischten Reihenfolge
    statt eines rein zufaelligen Treffers (siehe app/db.py:wissen_status_*) -
    jeder Eintrag kommt garantiert einmal dran, bevor sich die Reihenfolge
    wiederholt (dann neu gemischt). Global fuer alle Nutzer gemeinsam, wie
    unnuetzes_wissen selbst auch kein benutzerspezifischer Inhalt ist."""
    alle = db.wissen_alle_lesen(settings.database_path)
    if not alle:
        raise HTTPException(404, "Kein unnützes Wissen vorhanden.")
    nach_id = {zeile["id"]: zeile for zeile in alle}
    alle_ids = list(nach_id.keys())

    reihenfolge, position = db.wissen_status_lesen(settings.database_path)
    position += 1
    # Neu mischen, wenn: noch nie gemischt, die Runde durchgelaufen ist,
    # oder sich der Datenbestand seit dem letzten Mischen veraendert hat
    # (z.B. neue Eintraege ergaenzt) - eine veraltete Reihenfolge koennte
    # sonst auf nicht mehr existierende IDs zeigen.
    if not reihenfolge or position >= len(reihenfolge) or set(reihenfolge) != set(alle_ids):
        reihenfolge = alle_ids[:]
        random.shuffle(reihenfolge)
        position = 0

    db.wissen_status_schreiben(settings.database_path, reihenfolge, position)

    zeile = nach_id[reihenfolge[position]]
    daten = dict(zeile)
    daten["nummer"] = daten.pop("id")
    return WissenNaechstesAntwort(eintrag=WissenEintrag(**daten), position=position + 1, gesamt=len(reihenfolge))
