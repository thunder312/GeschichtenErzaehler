"""Login/Logout/aktueller-Benutzer - siehe app/auth.py fuer Hashing und die
get_current_user-Dependency, die alle anderen Router schuetzt."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app import db
from app.auth import get_current_user, passwort_pruefen, session_token_erzeugen
from app.config import Settings, get_settings
from app.schemas import Benutzer, LoginEingabe

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Benutzer)
def login(eingabe: LoginEingabe, response: Response, settings: Settings = Depends(get_settings)):
    zeile = db.benutzer_by_username(settings.database_path, eingabe.username)
    if not zeile or not passwort_pruefen(eingabe.password, zeile["password_hash"]):
        raise HTTPException(401, "Benutzername oder Passwort falsch.")

    token = session_token_erzeugen()
    db.session_anlegen(settings.database_path, token, zeile["id"])
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_tage * 86400,
        path="/",
    )
    return Benutzer(id=zeile["id"], username=zeile["username"], ist_admin=bool(zeile["ist_admin"]))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, settings: Settings = Depends(get_settings),
           _benutzer: Benutzer = Depends(get_current_user)):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        db.session_loeschen(settings.database_path, token)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=Benutzer)
def me(benutzer: Benutzer = Depends(get_current_user)):
    return benutzer
