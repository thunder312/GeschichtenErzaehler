"""Zentrale Konfiguration des Backends.

Uebernimmt die Rolle der Umgebungsvariablen aus novelle.py (OLLAMA_URL,
NOVELLE_PROJEKT, ...), aber GUI-gerecht gebuendelt statt pro Prozessaufruf
gesetzt: Projekte werden nicht mehr ueber das aktuelle Arbeitsverzeichnis
identifiziert, sondern liegen alle unter PROJECTS_DIR, ein Unterordner pro
Geschichte (Ordnername = Vertrag aus Schnittstellen-Uebersicht Abschnitt 1).
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVELLE_", env_file=".env", extra="ignore")

    # Default-Ollama-Ziel, falls eine Anfrage kein explizites SSH-Ziel angibt
    # (z.B. lokal laufendes Ollama waehrend der Entwicklung).
    ollama_url: str = "http://localhost:11434"

    # Wurzelverzeichnis aller Story-Projekte. Jeder Unterordner entspricht
    # einem Projektordner aus dem CLI-Vertrag (geruest.md, kapitel_NN.md, ...).
    projects_dir: Path = BACKEND_DIR / "instance" / "projects"

    # Epochenlose Basis-Personas + Epochen-Bibliothek, identisch zum
    # zentralen Skript-Ordner-Konzept von novelle.py, hier fest im Backend
    # mitgeliefert statt ueber Path(__file__) am Skript-Ort gesucht.
    shared_personas_dir: Path = APP_DIR / "data" / "personas"
    epochen_dir: Path = APP_DIR / "data" / "epochen"

    # SQLite-Datenbank fuer SSH-Ziele und Projekt-Metadaten (Autor-Modell-
    # Overrides, zuletzt verwendetes SSH-Ziel je Projekt, etc.)
    database_path: Path = BACKEND_DIR / "instance" / "novelle_gui.db"

    # Datei mit dem lokalen Fernet-Schluessel zur Verschluesselung von SSH-
    # Zugangsdaten (Passwoerter/Passphrasen) in der SQLite-DB. Wird bei
    # erstem Start automatisch erzeugt, siehe app/security.py.
    secret_key_path: Path = BACKEND_DIR / "instance" / ".secret_key"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Haeppchen "unnuetzes Wissen" rund ums Bücherschreiben, die waehrend
    # laengerer KI-Wartezeiten im Frontend eingeblendet werden (siehe
    # app/api/wissen.py). Pipe-getrennt statt echtes CSV, weil die
    # Kuriositaets-/Hintergrundtexte oft Kommas enthalten.
    unnuetzes_wissen_csv: Path = REPO_DIR / "docs" / "unnützesWissen.csv"

    # Dokumentation, die das Frontend als gerendertes HTML in einem neuen
    # Tab oeffnet (siehe app/api/dokumentation.py).
    anleitung_md: Path = REPO_DIR / "docs" / "Anleitung.md"
    hilfe_md: Path = REPO_DIR / "docs" / "Hilfe.md"

    # Login-Zugang (siehe app/auth.py). Waehrend Entwicklung/Test bewusst
    # inaktiv (get_current_user liefert dann transparent default_username) -
    # erst kurz vor dem echten Deploy auf True stellen.
    auth_aktiv: bool = False
    default_username: str = "daniel"
    session_cookie_name: str = "ge_session"
    session_ttl_tage: int = 30
    # Erst im Prod-Deploy (HTTPS) auf True stellen - im lokalen http://
    # Dev-Betrieb wuerde der Browser ein "Secure"-Cookie sonst verwerfen.
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
