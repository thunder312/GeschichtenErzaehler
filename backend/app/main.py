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
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import architekt, epochen, pipeline, projects, ssh_targets
from app.config import get_settings
from app.core.ollama_client import OllamaFehler
from app.core.projekt_dateien import DateiFehlt
from app.core.ssh_manager import SSHVerbindungsFehler
from app.db import init_db

settings = get_settings()
init_db(settings.database_path)

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


app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(ssh_targets.router)
app.include_router(architekt.router)
app.include_router(epochen.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
