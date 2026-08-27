import pytest
from fastapi.testclient import TestClient

from app.api import pipeline as api_pipeline
from app.config import Settings, get_settings
from app.core import projekt_dateien as pd
from app.db import init_db
from app.main import app
from app.schemas import Befund, BefundBeschreibung, BefundeAntwort
from app.services import projekt_pfad


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def projekt(client):
    r = client.post("/api/projects", json={"titel": "Testprojekt", "epoche": "Regency"})
    return r.json()["ordner"]


def _konflikt_befund_anlegen(projekt: str) -> None:
    settings = app.dependency_overrides[get_settings]()
    projekt_root = projekt_pfad(settings, settings.default_username, projekt) / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_root, 1), "Vorher. Nachdem sie das Café verlassen hatten. Nachher.")
    antwort = BefundeAntwort(
        kapitel=1, erzeugt_am="2026-08-27 08:00", jahr="2005",
        befunde=[
            Befund(
                id="b1",
                kategorien=["anachronismus", "kontinuitaet"],
                fundstelle="Nachdem sie das Café verlassen hatten.",
                beschreibungen=[
                    BefundBeschreibung(quelle="anachronismus", text="'Café' ist zu modern."),
                    BefundBeschreibung(quelle="kontinuitaet", text="Der Übergang ist zu abrupt."),
                ],
                sicherheit="hoch",
                vorschlag=None,
                konflikt=True,
                konflikt_vorschlaege=[
                    BefundBeschreibung(quelle="anachronismus", text="Nachdem sie die Taverne verlassen hatten."),
                    BefundBeschreibung(quelle="kontinuitaet", text="Nachdem sie das Café langsam verlassen hatten."),
                ],
                gefunden=True,
                start=8,
                end=47,
            ),
        ],
        quelltext_sha256=None,
        veraltet=False,
    )
    pd.schreib(pd.befunde_datei(projekt_root, 1), antwort.model_dump_json(indent=2))


def test_befund_synthese_loest_konflikt_auf(client, projekt, monkeypatch):
    _konflikt_befund_anlegen(projekt)

    eingaben = []

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        eingaben.append((rolle, user))
        return "Nachdem sie die Taverne langsam verlassen hatten.", {}

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)

    r = client.post(f"/api/projects/{projekt}/befunde/1/b1/synthese")
    assert r.status_code == 200
    befund = r.json()
    assert befund["vorschlag"] == "Nachdem sie die Taverne langsam verlassen hatten."
    assert befund["konflikt"] is False
    assert befund["konflikt_vorschlaege"] is not None  # Historie bleibt erhalten

    assert eingaben[0][0] == "befund_synthese"
    assert "ALTER TEXT" in eingaben[0][1]
    assert "Café" in eingaben[0][1]

    # Persistiert: erneutes Lesen der Befunde-Datei zeigt denselben Stand.
    r2 = client.get(f"/api/projects/{projekt}/befunde/1")
    assert r2.json()["befunde"][0]["vorschlag"] == "Nachdem sie die Taverne langsam verlassen hatten."
    assert r2.json()["befunde"][0]["konflikt"] is False


def test_befund_synthese_lehnt_verdaechtigen_vorschlag_ab(client, projekt, monkeypatch):
    _konflikt_befund_anlegen(projekt)

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return "Ersetzen Sie 'Café' durch ein passenderes Wort.", {}

    monkeypatch.setattr(api_pipeline, "_sammle_antwort", fake_sammle_antwort)

    r = client.post(f"/api/projects/{projekt}/befunde/1/b1/synthese")
    assert r.status_code == 502

    # Der Fund bleibt unveraendert ein Konflikt.
    r2 = client.get(f"/api/projects/{projekt}/befunde/1")
    assert r2.json()["befunde"][0]["konflikt"] is True


def test_befund_synthese_ohne_konflikt_liefert_400(client, projekt, monkeypatch):
    settings = app.dependency_overrides[get_settings]()
    projekt_root = projekt_pfad(settings, settings.default_username, projekt) / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_root, 1), "Ein normaler Satz.")
    antwort = BefundeAntwort(
        kapitel=1, erzeugt_am="2026-08-27 08:00", jahr="2005",
        befunde=[
            Befund(
                id="b1", kategorien=["lektorat"], fundstelle="Ein normaler Satz.",
                beschreibungen=[BefundBeschreibung(quelle="lektorat", text="Tippfehler.")],
                sicherheit="hoch", vorschlag="Ein normaler Satz!", konflikt=False,
                konflikt_vorschlaege=None, gefunden=True, start=0, end=18,
            ),
        ],
        quelltext_sha256=None, veraltet=False,
    )
    pd.schreib(pd.befunde_datei(projekt_root, 1), antwort.model_dump_json(indent=2))

    r = client.post(f"/api/projects/{projekt}/befunde/1/b1/synthese")
    assert r.status_code == 400
