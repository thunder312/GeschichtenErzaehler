"""Login/Session-Handling (siehe app/api/auth.py fuer die HTTP-Routen).

Passwort-Hashing ueber Argon2 (argon2-cffi) - bewusst nicht das schnelle
Einzelrunden-SHA256, das in einem anderen eigenen Projekt (myRecipes)
verwendet wird: Argon2 ist speicherhart und damit resistent gegen
GPU-gestuetztes Offline-Bruteforcing.

Sessions sind ein zufaelliges Opak-Token (keine JWT-Claims), das als
HttpOnly-Cookie im Browser liegt und serverseitig gegen die `sessions`-
Tabelle (siehe app/db.py) mit gleitendem Ablauf validiert wird.

get_current_user() ist die zentrale Dependency: solange
Settings.auth_aktiv False ist (Entwicklungs-/Testbetrieb, siehe ToDo.md),
liefert sie transparent einen festen Default-Benutzer, ohne dass irgendwo
sonst im Code zwischen "Auth an/aus" unterschieden werden muss.
"""
from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, WebSocket

from app import db
from app.config import Settings, get_settings
from app.schemas import Benutzer

_hasher = PasswordHasher()


def passwort_hashen(passwort: str) -> str:
    return _hasher.hash(passwort)


def passwort_pruefen(passwort: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, passwort)
    except VerifyMismatchError:
        return False


def session_token_erzeugen() -> str:
    return secrets.token_urlsafe(32)


def _benutzer_aus_token(token: str | None, settings: Settings) -> Benutzer:
    zeile = token and db.session_lesen(settings.database_path, token, settings.session_ttl_tage)
    if not zeile:
        raise HTTPException(401, "Nicht angemeldet.")
    db.session_beruehren(settings.database_path, token)
    return Benutzer(id=zeile["id"], username=zeile["username"], ist_admin=bool(zeile["ist_admin"]))


def get_current_user(request: Request, settings: Settings = Depends(get_settings)) -> Benutzer:
    """Fuer normale HTTP-Routen. Fuer WebSocket-Routen siehe
    get_current_user_ws() - FastAPI loest Depends()-Parameter vom Typ
    Request nicht innerhalb von @router.websocket(...) auf, nur WebSocket."""
    if not settings.auth_aktiv:
        return Benutzer(id=0, username=settings.default_username, ist_admin=True)
    return _benutzer_aus_token(request.cookies.get(settings.session_cookie_name), settings)


def get_current_user_ws(websocket: WebSocket, settings: Settings = Depends(get_settings)) -> Benutzer:
    if not settings.auth_aktiv:
        return Benutzer(id=0, username=settings.default_username, ist_admin=True)
    return _benutzer_aus_token(websocket.cookies.get(settings.session_cookie_name), settings)
