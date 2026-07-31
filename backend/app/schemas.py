"""Pydantic-Schemas fuer die REST-/WebSocket-API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EpocheKurz(BaseModel):
    name: str
    genre: str | None = None


class EpocheErstellenAnfrage(BaseModel):
    name: str = Field(min_length=1)
    genre: str = ""
    erfunden: bool
    beschreibung: str = Field(min_length=1)
    zeitraum: str = Field(min_length=1)
    orte: str = Field(min_length=1)
    gesellschaft: str = Field(min_length=1)
    statusregel: str = Field(min_length=1)
    rang_wort: str = ""
    anreden: str = ""
    nebenstrang_typen: str = ""
    vorbild_franchise: str = ""
    verbote_start: str = ""


class EpocheErstellenAntwort(BaseModel):
    name: str
    ordner: str
    dateien: dict[str, str]


class ProjektKurz(BaseModel):
    ordner: str
    titel: str | None = None
    epoche: str | None = None
    anzahl_kapitel: int
    letztes_geplantes_kapitel: int | None = None


class ProjektAnlegenAnfrage(BaseModel):
    # Leer erlaubt: der Titel ergibt sich haeufig erst aus dem Architekten-
    # Interview - siehe projekt_anlegen() in app/api/projects.py, das dann
    # ersatzweise den Platzhalter-Ordnernamen "neu" verwendet.
    titel: str = ""
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
    name: str = Field(min_length=1)
    # Fuer auth_method='direct' enthaelt 'host' die komplette Basis-URL
    # (z.B. 'http://192.168.1.50:11434') statt eines SSH-Hostnamens -
    # username/port/remote_ollama_port bleiben dann unbenutzt.
    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = ""
    auth_method: Literal["password", "private_key", "agent", "direct"]
    password: str | None = None
    private_key_pem: str | None = None
    private_key_passphrase: str | None = None
    remote_ollama_port: int = Field(default=11434, ge=1, le=65535)


class SSHZielAntwort(BaseModel):
    id: str
    name: str
    host: str
    port: int
    username: str
    auth_method: str
    remote_ollama_port: int
    favorit: bool
    created_at: str
    updated_at: str


class SSHZielFavoritAnfrage(BaseModel):
    favorit: bool


class SSHTestAnfrage(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = ""
    auth_method: Literal["password", "private_key", "agent", "direct"]
    password: str | None = None
    private_key_pem: str | None = None
    private_key_passphrase: str | None = None
    remote_ollama_port: int = Field(default=11434, ge=1, le=65535)


class SSHTestAntwort(BaseModel):
    erfolgreich: bool
    meldung: str


class OllamaModellInfo(BaseModel):
    name: str
    parameter_size: str | None = None
    size_bytes: int | None = None


class PersonaModellAntwort(BaseModel):
    persona: str
    default_modell: str
    override_modell: str | None
    effektives_modell: str


class PersonaModellSetzenAnfrage(BaseModel):
    modell: str | None = None


class Finding(BaseModel):
    code: str
    meldung: str
    schwere: str


class BefundBeschreibung(BaseModel):
    quelle: str
    text: str


class Befund(BaseModel):
    """Ein (ggf. aus mehreren Pruefer-Funden zusammengefuehrter) Fund - siehe
    app/core/befunde_merge.py fuer die Zusammenfuehrungs-Logik und
    app/core/fundstellen.py fuer die Ermittlung von start/end."""
    id: str
    kategorien: list[str]
    fundstelle: str
    beschreibungen: list[BefundBeschreibung]
    sicherheit: str | None
    vorschlag: str | None
    konflikt: bool
    konflikt_vorschlaege: list[BefundBeschreibung] | None = None
    gefunden: bool
    start: int | None
    end: int | None


class BefundeAntwort(BaseModel):
    kapitel: int
    erzeugt_am: str
    jahr: str | None
    befunde: list[Befund]
    # SHA-256 des Kapiteltexts, gegen den die start/end-Offsets in `befunde`
    # berechnet wurden - erlaubt es, beim spaeteren Lesen (befunde_lesen())
    # zu erkennen, ob der Kapiteltext seither ueberschrieben wurde und die
    # Offsets damit veraltet sind. None nur bei vor Einfuehrung dieses Felds
    # geschriebenen befunde_*.json-Dateien.
    quelltext_sha256: str | None = None
    # Wird nicht mitgeschrieben, sondern erst beim Lesen (befunde_lesen())
    # anhand von quelltext_sha256 gesetzt.
    veraltet: bool = False


class RechtschreibWort(BaseModel):
    wort: str
    satz: str | None


class RechtschreibAntwort(BaseModel):
    unbekannte_woerter: list[RechtschreibWort]
    hunspell_verfuegbar: bool


class EinstellungenAntwort(BaseModel):
    projects_dir: str
    ist_standard: bool
    standard_projects_dir: str
    unterordner_je_epoche: bool


class FundusImportAntwort(BaseModel):
    importierte_projekte: int
    gefundene_figuren: int
    uebersprungen: list[str]


class EinstellungenAnfrage(BaseModel):
    # Leer/None setzt den Override zurueck auf standard_projects_dir.
    projects_dir: str | None = None
    unterordner_je_epoche: bool = False


class WissenEintrag(BaseModel):
    nummer: int
    kategorie: str
    thema: str
    kuriositaet: str
    hintergrund: str
    quelle: str | None = None


class Benutzer(BaseModel):
    id: int
    username: str
    ist_admin: bool


class LoginEingabe(BaseModel):
    username: str
    password: str


class BenutzerEintrag(BaseModel):
    id: int
    username: str
    ist_admin: bool
    created_at: str


class BenutzerAnlegenAnfrage(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=8)
    ist_admin: bool = False
