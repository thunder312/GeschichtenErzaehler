import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings, get_settings
from app.core.wissen import csv_einlesen
from app.db import init_db
from app.main import app


def test_csv_einlesen_parst_pipe_getrennte_datei(tmp_path):
    datei = tmp_path / "wissen.csv"
    datei.write_text(
        "Kategorie|Thema|Kuriositaet|Hintergrund|Quelle\n"
        "Autoren-Macken|Testautor|Kurioses Detail|Ein erklaerender Hintergrundtext.|https://example.org\n",
        encoding="utf-8",
    )

    eintraege = csv_einlesen(datei)

    assert eintraege == [{
        "kategorie": "Autoren-Macken",
        "thema": "Testautor",
        "kuriositaet": "Kurioses Detail",
        "hintergrund": "Ein erklaerender Hintergrundtext.",
        "quelle": "https://example.org",
    }]


def test_csv_einlesen_ohne_datei_liefert_leere_liste(tmp_path):
    assert csv_einlesen(tmp_path / "fehlt.csv") == []


def test_csv_einlesen_erkennt_cp1252_faellt_zurueck(tmp_path):
    # docs/unnützesWissen.csv liegt in diesem Setup als cp1252 vor (z.B. mit
    # Windows-Editoren gespeichert) statt als UTF-8 - ohne Fallback wuerden
    # Umlaute als Mojibake/"?" ankommen.
    datei = tmp_path / "wissen.csv"
    inhalt = "Kategorie|Thema|Kuriositaet|Hintergrund|Quelle\nTest|Ä-Test|Ümlaut-Kuriositaet|Ein Straße-Hintergrund.|\n"
    datei.write_bytes(inhalt.encode("cp1252"))

    eintraege = csv_einlesen(datei)

    assert eintraege[0]["thema"] == "Ä-Test"
    assert eintraege[0]["kuriositaet"] == "Ümlaut-Kuriositaet"
    assert eintraege[0]["hintergrund"] == "Ein Straße-Hintergrund."


@pytest.fixture
def db_pfad(tmp_path):
    return tmp_path / "novelle_gui.db"


@pytest.fixture
def client(tmp_path, db_pfad):
    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=db_pfad,
        secret_key_path=tmp_path / ".secret_key",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_wissen_auflisten_liefert_vorab_eingefuegte_eintraege(client, db_pfad):
    db.wissen_einfuegen(db_pfad, [{
        "kategorie": "Autoren-Macken",
        "thema": "Testautor",
        "kuriositaet": "Kurioses Detail",
        "hintergrund": "Hintergrundtext.",
        "quelle": "https://example.org",
    }])

    r = client.get("/api/unnuetzeswissen")
    assert r.status_code == 200
    daten = r.json()
    assert len(daten) == 1
    assert daten[0]["nummer"] == 1
    assert daten[0]["thema"] == "Testautor"
    assert daten[0]["kuriositaet"] == "Kurioses Detail"


def test_wissen_auflisten_nummeriert_eintraege_fortlaufend(client, db_pfad):
    db.wissen_einfuegen(db_pfad, [
        {"kategorie": "A", "thema": "Erstes", "kuriositaet": "x", "hintergrund": "x", "quelle": None},
        {"kategorie": "B", "thema": "Zweites", "kuriositaet": "x", "hintergrund": "x", "quelle": None},
    ])

    daten = client.get("/api/unnuetzeswissen").json()

    assert [d["nummer"] for d in daten] == [1, 2]


def test_wissen_auflisten_ohne_eintraege_liefert_leere_liste(client):
    r = client.get("/api/unnuetzeswissen")
    assert r.status_code == 200
    assert r.json() == []
