"""FastAPI-Einstiegspunkt. Start (Entwicklung):

    cd backend
    python -m venv .venv && .venv\\Scripts\\activate   (Windows)
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000

Das Frontend (siehe /frontend) laeuft im Dev-Betrieb separat unter Vite
(Port 5173) und spricht dieses Backend unter http://localhost:8000 an
(CORS ist dafuer in app/config.py freigeschaltet). Fuer einen gebauten
Produktions-Build kann das Vite-dist/-Verzeichnis spaeter zusaetzlich hier
gemountet werden.
"""
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import architekt, auth, benutzer, dokumentation, einstellungen, epochen, fundus, pipeline, projects, ssh_targets, wissen
from app.auth import get_current_admin, get_current_user
from app.config import get_settings
from app.core.ollama_client import OllamaFehler
from app.core.projekt_dateien import DateiFehlt
from app.core.ssh_manager import SSHVerbindungsFehler
from app.core.wissen import csv_einlesen
from app.db import init_db, wissen_anzahl, wissen_einfuegen
from app.migration import layout_migrieren

settings = get_settings()
init_db(settings.database_path)
layout_migrieren(settings)

# Einmalig beim Start befuellen, falls die Tabelle noch leer ist (z.B. beim
# allerersten Start oder nach dem Loeschen der DB-Datei) - kein Neu-Einlesen
# bei jedem Reload, damit Aenderungen an der DB (falls je gewuenscht) nicht
# staendig ueberschrieben werden.
if wissen_anzahl(settings.database_path) == 0:
    eintraege = csv_einlesen(settings.unnuetzes_wissen_csv)
    if eintraege:
        wissen_einfuegen(settings.database_path, eintraege)

app = FastAPI(title="Geschichten Erzähler Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Zentrale Fehlerbehandlung: ohne diese Handler wuerden OllamaFehler/
# DateiFehlt/SSHVerbindungsFehler, die aus tiefer verschachtelten
# Funktionen (core/*) aufsteigen, als nackte "Internal Server Error" (500,
# ohne verwertbare Meldung) beim Frontend ankommen - z.B. wenn ein
# REST-Endpunkt wie /pruefen ohne SSH-Ziel aufgerufen wird und das lokale
# Ollama nicht erreichbar ist. Die WebSocket-Endpunkte (schreiben,
# architekt) fangen dieselben Fehler bereits selbst ab, da sie eigene
# Nachrichten ueber den Socket schicken muessen statt einer HTTP-Antwort.
@app.exception_handler(OllamaFehler)
async def ollama_fehler_handler(_request: Request, exc: OllamaFehler) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(SSHVerbindungsFehler)
async def ssh_fehler_handler(_request: Request, exc: SSHVerbindungsFehler) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"SSH-Verbindung fehlgeschlagen: {exc}"})


@app.exception_handler(DateiFehlt)
async def datei_fehlt_handler(_request: Request, exc: DateiFehlt) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


app.include_router(auth.router)

# projects/pipeline/architekt lesen den eingeloggten Benutzer selbst per
# Depends(get_current_user) aus (siehe app/services.py - Projekt-Pfade
# werden pro Username verschachtelt), deshalb hier KEIN zusaetzliches
# router-weites dependencies=[...] noetig. Die uebrigen Router betreffen
# keine Projekt-Daten und brauchen den Benutzer selbst nicht - dort reicht
# der reine Seiteneffekt "ueberhaupt eingeloggt" (oder Dev-Bypass).
app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(architekt.router)
app.include_router(ssh_targets.router, dependencies=[Depends(get_current_user)])
app.include_router(epochen.router, dependencies=[Depends(get_current_user)])
# einstellungen (Speicherort) und benutzer (Benutzerverwaltung) sind
# vollstaendig Admin-Benutzern vorbehalten (siehe ToDo.md: Tabs "KI-Ziele",
# "Einstellungen", "Benutzer" nur fuer Admins sichtbar) - bei ssh_targets ist
# nur die Liste (GET) fuer alle eingeloggten Benutzer offen, siehe dortige
# einzelne Endpunkt-Dependencies.
app.include_router(einstellungen.router, dependencies=[Depends(get_current_admin)])
app.include_router(benutzer.router, dependencies=[Depends(get_current_admin)])
app.include_router(wissen.router, dependencies=[Depends(get_current_user)])
app.include_router(dokumentation.router, dependencies=[Depends(get_current_user)])
# fundus liest benutzer.username selbst per Depends(get_current_user) aus
# (analog projects/pipeline/architekt), deshalb kein zusaetzliches
# router-weites dependencies=[...] noetig.
app.include_router(fundus.router)
# Catch-All-Route fuer die Projekt-Detailansicht ("/{ordner:path}", matcht
# jeden Rest-Pfad) - muss als LETZTES eingebunden werden, sonst verdeckt sie
# spezifischere Routen aus pipeline/architekt (siehe Kommentar in
# app/api/projects.py bei fallback_router).
app.include_router(projects.fallback_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
