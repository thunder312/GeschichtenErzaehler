"""Pydantic-Schemas fuer die REST-/WebSocket-API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EpocheKurz(BaseModel):
    name: str


class ProjektKurz(BaseModel):
    ordner: str
    titel: str | None = None
    epoche: str | None = None
    anzahl_kapitel: int
    letztes_geplantes_kapitel: int | None = None


class ProjektAnlegenAnfrage(BaseModel):
    titel: str = Field(min_length=1)
    epoche: str


class ProjektDetail(BaseModel):
    ordner: str
    epoche: str | None
    geruest: str | None
    verbotsliste: str | None
    kapitel: list[int]
    jahr: str | None = None
    jugendschutz_stufe: str | None = None
    autor_modell: str | None = None
    automatische_fortsetzung: bool | None = None
    letztes_geplantes_kapitel: int | None = None
    kapitelplan: dict[int, int] = {}


class GeruestSchreibenAnfrage(BaseModel):
    inhalt: str


class SchreibenAnfrage(BaseModel):
    zusatzhinweis: str = ""
    ssh_ziel_id: str | None = None


class SSHZielAnlegenAnfrage(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    auth_method: str  # "password" | "private_key" | "agent"
    password: str | None = None
    private_key_pem: str | None = None
    private_key_passphrase: str | None = None
    remote_ollama_port: int = 11434


class SSHZielAntwort(BaseModel):
    id: str
    name: str
    host: str
    port: int
    username: str
    auth_method: str
    remote_ollama_port: int
    created_at: str
    updated_at: str


class SSHTestAnfrage(BaseModel):
    host: str
    port: int = 22
    username: str
    auth_method: str
    password: str | None = None
    private_key_pem: str | None = None
    private_key_passphrase: str | None = None
    remote_ollama_port: int = 11434


class SSHTestAntwort(BaseModel):
    erfolgreich: bool
    meldung: str


class Finding(BaseModel):
    code: str
    meldung: str
    schwere: str


class BefundeAntwort(BaseModel):
    kapitel: int
    inhalt: str


class AnwendenAntwort(BaseModel):
    alt: str
    neu: str
    gesichert_als: str | None


class RechtschreibWort(BaseModel):
    wort: str
    satz: str | None


class RechtschreibAntwort(BaseModel):
    unbekannte_woerter: list[RechtschreibWort]
    hunspell_verfuegbar: bool
