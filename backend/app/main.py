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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import architekt, epochen, pipeline, projects, ssh_targets
from app.config import get_settings
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

app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(ssh_targets.router)
app.include_router(architekt.router)
app.include_router(epochen.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
