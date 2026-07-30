import asyncio

import pytest

from app.api import architekt as api_arch
from app.config import Settings
from app.core import projekt_dateien as pd
from app.core.ollama_client import OllamaFehler
from app.db import init_db
from app.schemas import Benutzer

GERUEST_MIT_FIGUREN = (
    "# STORY-GERUEST\n\n"
    "## Titel\nDer Markt von Rothenfeld\n\n"
    "## Figuren\n"
    "Lady Amelia Hartwell, 24, Baronesse, will unabhaengig sein.\n\n"
    "## Konflikt\nSie will heiraten, ihr Vater verbietet es.\n"
)

GERUEST_OHNE_FIGUREN = "# STORY-GERUEST\n\n## Titel\nOhne Figuren\n\n## Rahmen\nJahr: 1815\n"


@pytest.fixture
def settings(tmp_path):
    s = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
    )
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(s.database_path)
    return s


@pytest.fixture
def benutzer():
    return Benutzer(id=1, username="daniel", ist_admin=True)


@pytest.fixture
def projekt_root(tmp_path):
    root = tmp_path / "projekt-ordner"
    root.mkdir()
    (root / ".epoche").write_text("Regency", encoding="utf-8")
    return root


def test_fundus_aktualisieren_schreibt_figuren_bei_erfolg(settings, benutzer, projekt_root, monkeypatch):
    async def fake_sammle_antwort(base_url, rolle, system, user, format=None):
        return (
            '{"figuren": [{"name": "Lady Amelia Hartwell", "alter": "24", '
            '"stand": "Baronesse", "eigenschaften": "will unabhaengig sein"}]}',
            {},
        )

    monkeypatch.setattr(api_arch, "sammle_antwort", fake_sammle_antwort)

    asyncio.run(api_arch._fundus_aktualisieren(settings, benutzer, projekt_root, "http://fake", GERUEST_MIT_FIGUREN))

    from app.services import fundus_datei
    inhalt = pd.lies(fundus_datei(settings, benutzer.username))
    assert "## Regency" in inhalt
    assert "### Lady Amelia Hartwell" in inhalt
    assert "Der Markt von Rothenfeld" in inhalt


def test_fundus_aktualisieren_ist_nicht_fatal_bei_ollama_fehler(settings, benutzer, projekt_root, monkeypatch):
    async def fake_sammle_antwort(base_url, rolle, system, user, format=None):
        raise OllamaFehler("Ollama nicht erreichbar")

    monkeypatch.setattr(api_arch, "sammle_antwort", fake_sammle_antwort)

    # Darf keine Exception werfen - der Architekten-Abschluss haengt bereits
    # davon ab, dass dieser Aufruf nicht fehlschlaegt.
    asyncio.run(api_arch._fundus_aktualisieren(settings, benutzer, projekt_root, "http://fake", GERUEST_MIT_FIGUREN))

    from app.services import fundus_datei
    assert not fundus_datei(settings, benutzer.username).exists()


def test_fundus_aktualisieren_ist_nicht_fatal_bei_kaputtem_json(settings, benutzer, projekt_root, monkeypatch):
    async def fake_sammle_antwort(base_url, rolle, system, user, format=None):
        return "kein json{{{", {}

    monkeypatch.setattr(api_arch, "sammle_antwort", fake_sammle_antwort)

    asyncio.run(api_arch._fundus_aktualisieren(settings, benutzer, projekt_root, "http://fake", GERUEST_MIT_FIGUREN))

    from app.services import fundus_datei
    assert not fundus_datei(settings, benutzer.username).exists()


def test_fundus_aktualisieren_ueberspringt_geruest_ohne_figuren_abschnitt(settings, benutzer, projekt_root, monkeypatch):
    aufgerufen = False

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None):
        nonlocal aufgerufen
        aufgerufen = True
        return "{}", {}

    monkeypatch.setattr(api_arch, "sammle_antwort", fake_sammle_antwort)

    asyncio.run(api_arch._fundus_aktualisieren(settings, benutzer, projekt_root, "http://fake", GERUEST_OHNE_FIGUREN))

    assert not aufgerufen


def test_fundus_aktualisieren_ueberspringt_projekt_ohne_epoche(settings, benutzer, tmp_path, monkeypatch):
    root_ohne_epoche = tmp_path / "kein-epoche-ordner"
    root_ohne_epoche.mkdir()
    aufgerufen = False

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None):
        nonlocal aufgerufen
        aufgerufen = True
        return "{}", {}

    monkeypatch.setattr(api_arch, "sammle_antwort", fake_sammle_antwort)

    asyncio.run(api_arch._fundus_aktualisieren(settings, benutzer, root_ohne_epoche, "http://fake", GERUEST_MIT_FIGUREN))

    assert not aufgerufen


def test_fundus_kontext_haengt_epoche_abschnitt_an(settings, benutzer, projekt_root):
    from app.services import fundus_datei
    pd.schreib(fundus_datei(settings, benutzer.username), "## Regency\n\n### Lady Amelia\n- Alter: 24\n")

    kontext = api_arch._fundus_kontext(settings, benutzer, projekt_root)
    assert "FUNDUS DIESER EPOCHE" in kontext
    assert "Lady Amelia" in kontext


def test_fundus_kontext_ist_leer_ohne_fundus_datei(settings, benutzer, projekt_root):
    assert api_arch._fundus_kontext(settings, benutzer, projekt_root) == ""
