"""Unnuetzes Wissen rund ums Buecherschreiben, das beim Start (siehe
app/main.py) einmalig aus docs/unnützesWissen.csv in die DB geladen wird -
fuer das Zeit-Ueberbrueckungs-Overlay im Frontend waehrend laengerer
KI-Wartezeiten."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app import db
from app.config import Settings, get_settings
from app.schemas import WissenEintrag

router = APIRouter(prefix="/api/unnuetzeswissen", tags=["wissen"])


@router.get("", response_model=list[WissenEintrag])
def wissen_auflisten(settings: Settings = Depends(get_settings)):
    return [WissenEintrag(**dict(zeile)) for zeile in db.wissen_alle_lesen(settings.database_path)]
