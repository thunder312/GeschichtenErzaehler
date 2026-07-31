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


def test_wissen_status_lesen_ohne_vorherigen_lauf_liefert_leerzustand(db_pfad):
    init_db(db_pfad)
    reihenfolge, position = db.wissen_status_lesen(db_pfad)
    assert reihenfolge == []
    assert position == -1


def test_wissen_status_schreiben_und_lesen_roundtrip(db_pfad):
    init_db(db_pfad)
    db.wissen_status_schreiben(db_pfad, [3, 1, 2], 1)
    reihenfolge, position = db.wissen_status_lesen(db_pfad)
    assert reihenfolge == [3, 1, 2]
    assert position == 1

    db.wissen_status_schreiben(db_pfad, [3, 1, 2], 2)
    _, position2 = db.wissen_status_lesen(db_pfad)
    assert position2 == 2


def _fuenf_eintraege_einfuegen(db_pfad):
    db.wissen_einfuegen(db_pfad, [
        {"kategorie": "A", "thema": f"Thema {i}", "kuriositaet": "x", "hintergrund": "x", "quelle": None}
        for i in range(5)
    ])


def test_wissen_naechstes_ohne_eintraege_gibt_404(client):
    r = client.get("/api/unnuetzeswissen/naechstes")
    assert r.status_code == 404


def test_wissen_naechstes_liefert_jeden_eintrag_genau_einmal_pro_runde(client, db_pfad):
    _fuenf_eintraege_einfuegen(db_pfad)

    gesehene_nummern = []
    for _ in range(5):
        antwort = client.get("/api/unnuetzeswissen/naechstes").json()
        gesehene_nummern.append(antwort["eintrag"]["nummer"])
        assert antwort["gesamt"] == 5

    assert sorted(gesehene_nummern) == [1, 2, 3, 4, 5]
    assert len(set(gesehene_nummern)) == 5  # keine Wiederholung innerhalb der Runde


def test_wissen_naechstes_startet_nach_voller_runde_neue_mischung(client, db_pfad):
    _fuenf_eintraege_einfuegen(db_pfad)

    erste_runde = [client.get("/api/unnuetzeswissen/naechstes").json() for _ in range(5)]
    assert [a["position"] for a in erste_runde] == [1, 2, 3, 4, 5]

    naechste = client.get("/api/unnuetzeswissen/naechstes").json()
    # Neue Runde faengt wieder bei Position 1 an, mit vollstaendiger Laenge.
    assert naechste["position"] == 1
    assert naechste["gesamt"] == 5


def test_wissen_naechstes_reagiert_auf_neue_eintraege_waehrend_einer_runde(client, db_pfad):
    _fuenf_eintraege_einfuegen(db_pfad)
    client.get("/api/unnuetzeswissen/naechstes")  # eine Runde von 5 anstossen

    db.wissen_einfuegen(db_pfad, [
        {"kategorie": "B", "thema": "Neu", "kuriositaet": "x", "hintergrund": "x", "quelle": None},
    ])

    # Gesamtzahl der gespeicherten Reihenfolge muss sich an den neuen
    # Datenbestand (6 statt 5) anpassen, statt an der veralteten Laenge
    # festzuhalten oder auf eine nicht mehr passende ID zu zeigen.
    gesehen = set()
    for _ in range(6):
        antwort = client.get("/api/unnuetzeswissen/naechstes").json()
        gesehen.add(antwort["eintrag"]["nummer"])
    assert gesehen == {1, 2, 3, 4, 5, 6}
