import pytest
from fastapi.testclient import TestClient

from app.api import fundus as api_fundus
from app.config import Settings, get_settings
from app.db import init_db
from app.main import app


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


def test_fundus_lesen_liefert_leere_vorlage_ohne_vorhandene_datei(client):
    r = client.get("/api/fundus")
    assert r.status_code == 200
    assert "FUNDUS-VORLAGE" in r.text


def test_fundus_schreiben_und_wieder_lesen(client):
    inhalt = "## Regency\n\n### Lady Amelia\n- Alter: 24\n- Geschichten: Testgeschichte\n"
    r = client.put("/api/fundus", json={"inhalt": inhalt})
    assert r.status_code == 200

    r2 = client.get("/api/fundus")
    assert r2.text.strip() == inhalt.strip()


def test_fundus_schreiben_sichert_vorherige_fassung_als_bak(client, tmp_path):
    client.put("/api/fundus", json={"inhalt": "Erste Fassung"})
    r = client.put("/api/fundus", json={"inhalt": "Zweite Fassung"})
    assert r.json()["gesichert_als"] is not None

    fundus_datei = tmp_path / "projects" / "daniel" / "fundus.md"
    assert fundus_datei.read_text(encoding="utf-8").strip() == "Zweite Fassung"
    sicherungen = list(fundus_datei.parent.glob("fundus.md.*.bak"))
    assert len(sicherungen) == 1
    assert sicherungen[0].read_text(encoding="utf-8").strip() == "Erste Fassung"


def test_fundus_import_ueberspringt_projekte_ohne_figuren_abschnitt(client):
    r = client.post("/api/projects", json={"titel": "Projekt ohne Figuren", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nOhne Figuren\n\n## Rahmen\nJahr: 1815\n",
    })

    r2 = client.post("/api/fundus/import")
    assert r2.status_code == 200
    daten = r2.json()
    assert daten["importierte_projekte"] == 0
    assert daten["gefundene_figuren"] == 0
    assert len(daten["uebersprungen"]) == 1


def test_fundus_import_extrahiert_figuren_aus_geruest(client, monkeypatch):
    r = client.post("/api/projects", json={"titel": "Der Markt von Rothenfeld", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n\n"
                  "## Figuren\nLady Amelia Hartwell, 24, Baronesse, eigensinnig.\n\n"
                  "## Konflikt\nSie will heiraten, ihr Vater verbietet es.\n",
    })

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return (
            '{"figuren": [{"name": "Lady Amelia Hartwell", "alter": "24", '
            '"stand": "Baronesse", "eigenschaften": "eigensinnig"}]}',
            {},
        )

    monkeypatch.setattr(api_fundus, "sammle_antwort", fake_sammle_antwort)

    r2 = client.post("/api/fundus/import")
    assert r2.status_code == 200
    daten = r2.json()
    assert daten["importierte_projekte"] == 1
    assert daten["gefundene_figuren"] == 1
    assert daten["uebersprungen"] == []

    r3 = client.get("/api/fundus")
    assert "## Regency" in r3.text
    assert "### Lady Amelia Hartwell" in r3.text
    assert "Der Markt von Rothenfeld" in r3.text


def test_fundus_projekt_aktualisieren_ueberspringt_projekt_ohne_figuren_abschnitt(client):
    # Titel identisch zum Anlege-Titel halten, sonst benennt das PUT unten
    # den Projektordner um (siehe app/api/projects.py:geruest_schreiben) und
    # "ordner" zeigt danach ins Leere.
    r = client.post("/api/projects", json={"titel": "Ohne Figuren", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nOhne Figuren\n\n## Rahmen\nJahr: 1815\n",
    })

    r2 = client.post(f"/api/fundus/projekt/{ordner}")
    assert r2.status_code == 200
    daten = r2.json()
    assert daten["gefundene_figuren"] == 0
    assert daten["uebersprungen"] is True


def test_fundus_projekt_aktualisieren_extrahiert_nur_figuren_dieses_projekts(client, monkeypatch):
    r1 = client.post("/api/projects", json={"titel": "Ohne Figuren zweitens", "epoche": "Regency"})
    ordner_ohne = r1.json()["ordner"]
    client.put(f"/api/projects/{ordner_ohne}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nOhne Figuren zweitens\n\n## Rahmen\nJahr: 1816\n",
    })

    r2 = client.post("/api/projects", json={"titel": "Der Markt von Rothenfeld", "epoche": "Regency"})
    ordner_mit = r2.json()["ordner"]
    client.put(f"/api/projects/{ordner_mit}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n\n"
                  "## Figuren\nLady Amelia Hartwell, 24, Baronesse, eigensinnig.\n\n"
                  "## Konflikt\nSie will heiraten, ihr Vater verbietet es.\n",
    })

    aufrufe = []

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        aufrufe.append(user)
        return (
            '{"figuren": [{"name": "Lady Amelia Hartwell", "alter": "24", '
            '"stand": "Baronesse", "eigenschaften": "eigensinnig"}]}',
            {},
        )

    monkeypatch.setattr(api_fundus, "sammle_antwort", fake_sammle_antwort)

    # Nur das Projekt MIT Figuren-Abschnitt anfragen - das andere Projekt
    # (ordner_ohne) darf dabei gar nicht erst per LLM abgeklappert werden
    # (anders als /api/fundus/import, das die komplette Bibliothek durchgeht).
    r3 = client.post(f"/api/fundus/projekt/{ordner_mit}")
    assert r3.status_code == 200
    daten = r3.json()
    assert daten["gefundene_figuren"] == 1
    assert daten["uebersprungen"] is False
    assert len(aufrufe) == 1

    r4 = client.get("/api/fundus")
    assert "### Lady Amelia Hartwell" in r4.text


def test_fundus_projekt_aktualisieren_verwirft_feld_bezeichner_als_figur(client, monkeypatch):
    # Regression (2026-08, "Dunkle-Geheimnisse-im-Gutshaus" auf Prod): die
    # Rolle "fundus_pfleger" trug bei einer dicht mit "Ziel: ... größte
    # Angst: ... Geheimnis: ... Entwicklungsbogen: ..." formulierten
    # Figuren-Referenz (Standard-Satzstruktur JEDER Epoche-Vorlage, siehe
    # app/core/fundus.py:_KEIN_FIGURENNAME) diese Feld-Bezeichner faelschlich
    # als eigene Figuren in den Fundus ein.
    r = client.post("/api/projects", json={"titel": "Dunkle Geheimnisse", "epoche": "Wilhelminisches Preußen"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDunkle Geheimnisse\n\n"
                  "## Figuren\nAgnes: Protagonistin. Ziel: Vergangenheit aufarbeiten. "
                  "größte Angst: Überwältigt werden. Geheimnis: Ihre Herkunft.\n\n"
                  "## Konflikt\nSie kehrt zurueck.\n",
    })

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return (
            '{"figuren": ['
            '{"name": "Agnes", "alter": "", "stand": "Protagonistin", "eigenschaften": "erschoepft"},'
            '{"name": "Ziel", "alter": "", "stand": "", "eigenschaften": "Vergangenheit aufarbeiten"},'
            '{"name": "Geheimnis", "alter": "", "stand": "", "eigenschaften": "Ihre Herkunft"}'
            ']}',
            {},
        )

    monkeypatch.setattr(api_fundus, "sammle_antwort", fake_sammle_antwort)

    r2 = client.post(f"/api/fundus/projekt/{ordner}")
    assert r2.status_code == 200
    daten = r2.json()
    assert daten["gefundene_figuren"] == 1
    assert daten["uebersprungen"] is False

    r3 = client.get("/api/fundus")
    assert "### Agnes" in r3.text
    assert "### Ziel" not in r3.text
    assert "### Geheimnis" not in r3.text


def test_fundus_projekt_aktualisieren_ueberspringt_wenn_nur_feld_bezeichner_gemeldet(client, monkeypatch):
    r = client.post("/api/projects", json={"titel": "Nur Feld-Bezeichner", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nNur Feld-Bezeichner\n\n"
                  "## Figuren\nZiel: unklar. Geheimnis: unklar.\n\n## Konflikt\nUnklar.\n",
    })

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return ('{"figuren": [{"name": "Ziel", "alter": "", "stand": "", "eigenschaften": "unklar"}]}', {})

    monkeypatch.setattr(api_fundus, "sammle_antwort", fake_sammle_antwort)

    r2 = client.post(f"/api/fundus/projekt/{ordner}")
    daten = r2.json()
    assert daten["gefundene_figuren"] == 0
    assert daten["uebersprungen"] is False

    r3 = client.get("/api/fundus")
    assert "### Ziel" not in r3.text
