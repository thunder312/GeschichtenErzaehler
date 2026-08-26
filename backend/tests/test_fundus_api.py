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
    # Neues Template: jedes Feld erscheint als eigene Zeile, auch leer.
    assert "- Aussehen: \n" in r3.text
    assert "- Ziel: \n" in r3.text
    assert "- Angst: \n" in r3.text
    assert "- Geheimnis: \n" in r3.text


def test_fundus_import_extrahiert_aussehen_ziel_angst_geheimnis_getrennt(client, monkeypatch):
    r = client.post("/api/projects", json={"titel": "Ein Verbotenes Verlangen", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nEin Verbotenes Verlangen\n\n"
                  "## Figuren\nLady Amelia Hartwell: 24, Baronesse, eigensinnig. "
                  "Ziel: unabhaengig leben. Groesste Angst: Armut. Geheimnis: liebt einen Baecker.\n\n"
                  "## Konflikt\nSie will heiraten, ihr Vater verbietet es.\n",
    })

    async def fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
        return (
            '{"figuren": [{"name": "Lady Amelia Hartwell", "alter": "24", "stand": "Baronesse", '
            '"eigenschaften": "eigensinnig", "aussehen": "", "ziel": "unabhaengig leben", '
            '"angst": "Armut", "geheimnis": "liebt einen Baecker"}]}',
            {},
        )

    monkeypatch.setattr(api_fundus, "sammle_antwort", fake_sammle_antwort)

    r2 = client.post("/api/fundus/import")
    assert r2.json()["gefundene_figuren"] == 1

    r3 = client.get("/api/fundus")
    assert "- Ziel: unabhaengig leben\n" in r3.text
    assert "- Angst: Armut\n" in r3.text
    assert "- Geheimnis: liebt einen Baecker\n" in r3.text
    assert "- Aussehen: \n" in r3.text


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


# --- Strukturierter Personen-Editor (GET/POST/PUT/DELETE /api/fundus/figuren, POST /api/fundus/felder) ---

def _fundus_seed(client, inhalt: str) -> None:
    client.put("/api/fundus", json={"inhalt": inhalt})


_ZWEI_FIGUREN = (
    "## Regency\n\n"
    "### Lady Amelia Hartwell\n"
    "- Alter: 24\n"
    "- Stand/Rolle: Baronesse\n"
    "- Eigenschaften: eigensinnig\n"
    "- Aussehen: \n"
    "- Ziel: \n"
    "- Angst: \n"
    "- Geheimnis: \n"
    "- Geschichten: Der Markt von Rothenfeld\n"
    "\n"
    "### Lord Whitmore\n"
    "- Alter: 30\n"
    "- Stand/Rolle: Earl\n"
    "- Eigenschaften: \n"
    "- Aussehen: \n"
    "- Ziel: \n"
    "- Angst: \n"
    "- Geheimnis: \n"
    "- Geschichten: Der Markt von Rothenfeld\n"
)


def test_fundus_figuren_lesen_liefert_strukturierte_liste(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.get("/api/fundus/figuren")
    assert r.status_code == 200
    daten = r.json()
    assert daten["standard_felder"] == ["Alter", "Stand/Rolle", "Eigenschaften", "Aussehen", "Ziel", "Angst",
                                         "Geheimnis", "Geschichten"]
    namen = [(f["epoche"], f["name"]) for f in daten["figuren"]]
    assert namen == [("Regency", "Lady Amelia Hartwell"), ("Regency", "Lord Whitmore")]
    amelia = daten["figuren"][0]
    assert amelia["felder"]["Alter"] == "24"
    assert amelia["felder"]["Stand/Rolle"] == "Baronesse"


def test_fundus_figuren_lesen_ohne_datei_liefert_leere_liste(client):
    r = client.get("/api/fundus/figuren")
    assert r.status_code == 200
    assert r.json()["figuren"] == []


def test_fundus_figur_anlegen(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.post("/api/fundus/figuren", json={
        "epoche": "Mittelalter", "name": "Bertram", "felder": {"Alter": "40", "Stand/Rolle": "Ritter"},
    })
    assert r.status_code == 201
    daten = r.json()
    assert daten["felder"]["Alter"] == "40"
    assert daten["felder"]["Geschichten"] == ""
    assert list(daten["felder"].keys())[-1] == "Geschichten"

    r2 = client.get("/api/fundus/figuren")
    namen = [(f["epoche"], f["name"]) for f in r2.json()["figuren"]]
    assert ("Mittelalter", "Bertram") in namen


def test_fundus_figur_anlegen_verweigert_feld_bezeichner_als_namen(client):
    r = client.post("/api/fundus/figuren", json={"epoche": "Regency", "name": "Ziel", "felder": {}})
    assert r.status_code == 400


def test_fundus_figur_anlegen_verweigert_duplikat(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.post("/api/fundus/figuren", json={"epoche": "Regency", "name": "lady amelia hartwell", "felder": {}})
    assert r.status_code == 409


def test_fundus_figur_aktualisieren_ersetzt_felder(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.put("/api/fundus/figuren", json={
        "epoche": "Regency", "name": "Lady Amelia Hartwell",
        "felder": {"Alter": "25", "Stand/Rolle": "Baronesse", "Eigenschaften": "eigensinnig, klug",
                   "Aussehen": "", "Ziel": "", "Angst": "", "Geheimnis": "", "Geschichten": "Der Markt von Rothenfeld"},
    })
    assert r.status_code == 200
    assert r.json()["felder"]["Alter"] == "25"
    assert r.json()["felder"]["Eigenschaften"] == "eigensinnig, klug"

    text = client.get("/api/fundus").text
    assert "- Alter: 25" in text
    assert "eigensinnig, klug" in text


def test_fundus_figur_aktualisieren_kann_umbenennen(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.put("/api/fundus/figuren", json={
        "epoche": "Regency", "name": "Lord Whitmore", "neuer_name": "Lord Marcus Whitmore",
        "felder": {"Alter": "30"},
    })
    assert r.status_code == 200
    assert r.json()["name"] == "Lord Marcus Whitmore"
    text = client.get("/api/fundus").text
    assert "### Lord Marcus Whitmore" in text
    assert "### Lord Whitmore\n" not in text


def test_fundus_figur_aktualisieren_verweigert_umbenennen_auf_bestehenden_namen(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.put("/api/fundus/figuren", json={
        "epoche": "Regency", "name": "Lord Whitmore", "neuer_name": "Lady Amelia Hartwell", "felder": {},
    })
    assert r.status_code == 409


def test_fundus_figur_aktualisieren_unbekannte_figur_gibt_404(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.put("/api/fundus/figuren", json={"epoche": "Regency", "name": "Nicht Vorhanden", "felder": {}})
    assert r.status_code == 404


def test_fundus_figur_loeschen(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.delete("/api/fundus/figuren", params={"epoche": "Regency", "name": "Lord Whitmore"})
    assert r.status_code == 200

    text = client.get("/api/fundus").text
    assert "Lord Whitmore" not in text
    assert "Lady Amelia Hartwell" in text


def test_fundus_figur_loeschen_unbekannte_figur_gibt_404(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.delete("/api/fundus/figuren", params={"epoche": "Regency", "name": "Nicht Vorhanden"})
    assert r.status_code == 404


def test_fundus_feld_hinzufuegen_nur_eine_person(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.post("/api/fundus/felder", json={
        "epoche": "Regency", "name": "Lady Amelia Hartwell", "feld_name": "Blutgruppe",
        "wert": "0 negativ", "fuer_alle": False,
    })
    assert r.status_code == 200
    daten = r.json()
    assert daten["felder"]["Blutgruppe"] == "0 negativ"
    # Direkt vor "Geschichten" eingefuegt, nicht ans Ende.
    schluessel = list(daten["felder"].keys())
    assert schluessel[-2:] == ["Blutgruppe", "Geschichten"]

    figuren = client.get("/api/fundus/figuren").json()["figuren"]
    whitmore = next(f for f in figuren if f["name"] == "Lord Whitmore")
    assert "Blutgruppe" not in whitmore["felder"]


def test_fundus_feld_hinzufuegen_fuer_alle(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    client.post("/api/fundus/felder", json={
        "epoche": "Regency", "name": "Lady Amelia Hartwell", "feld_name": "Blutgruppe",
        "wert": "0 negativ", "fuer_alle": True,
    })

    figuren = client.get("/api/fundus/figuren").json()["figuren"]
    amelia = next(f for f in figuren if f["name"] == "Lady Amelia Hartwell")
    whitmore = next(f for f in figuren if f["name"] == "Lord Whitmore")
    assert amelia["felder"]["Blutgruppe"] == "0 negativ"
    assert whitmore["felder"]["Blutgruppe"] == ""


def test_fundus_feld_hinzufuegen_unbekannte_figur_gibt_404(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.post("/api/fundus/felder", json={
        "epoche": "Regency", "name": "Nicht Vorhanden", "feld_name": "Blutgruppe", "wert": "", "fuer_alle": False,
    })
    assert r.status_code == 404


# --- Verschieben (PUT .../figuren mit neue_epoche) und Kopieren (POST .../figuren/kopieren) ---

def test_fundus_figur_verschieben_in_andere_epoche(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.put("/api/fundus/figuren", json={
        "epoche": "Regency", "name": "Lord Whitmore", "neue_epoche": "Mittelalter",
        "felder": {"Alter": "30", "Stand/Rolle": "Earl"},
    })
    assert r.status_code == 200
    assert r.json()["epoche"] == "Mittelalter"

    figuren = client.get("/api/fundus/figuren").json()["figuren"]
    namen = [(f["epoche"], f["name"]) for f in figuren]
    assert ("Mittelalter", "Lord Whitmore") in namen
    assert ("Regency", "Lord Whitmore") not in namen
    # Original nicht dupliziert - weiterhin nur 2 Figuren insgesamt.
    assert len(figuren) == 2

    text = client.get("/api/fundus").text
    assert "## Mittelalter" in text and "## Regency" in text
    mittelalter_index = text.index("## Mittelalter")
    assert "Lord Whitmore" in text[mittelalter_index:]


def test_fundus_figur_verschieben_verweigert_kollision_im_ziel(client):
    _fundus_seed(client, _ZWEI_FIGUREN + "\n## Mittelalter\n\n### Lord Whitmore\n- Alter: \n- Geschichten: \n")
    # Jetzt gibt es "Lord Whitmore" auch in Mittelalter - Verschieben von
    # Regency nach Mittelalter muss daran scheitern.
    r = client.put("/api/fundus/figuren", json={
        "epoche": "Regency", "name": "Lord Whitmore", "neue_epoche": "Mittelalter", "felder": {},
    })
    assert r.status_code == 409


def test_fundus_figur_verschieben_und_umbenennen_gleichzeitig(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.put("/api/fundus/figuren", json={
        "epoche": "Regency", "name": "Lord Whitmore", "neuer_name": "Graf Whitmore",
        "neue_epoche": "Mittelalter", "felder": {},
    })
    assert r.status_code == 200
    assert r.json() == {"epoche": "Mittelalter", "name": "Graf Whitmore", "felder": {}}


def test_fundus_figur_kopieren(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.post("/api/fundus/figuren/kopieren", json={
        "epoche": "Regency", "name": "Lady Amelia Hartwell", "ziel_epoche": "Mittelalter",
    })
    assert r.status_code == 201
    kopie = r.json()
    assert kopie["epoche"] == "Mittelalter"
    assert kopie["name"] == "Lady Amelia Hartwell"
    assert kopie["felder"]["Stand/Rolle"] == "Baronesse"
    assert kopie["felder"]["Geschichten"] == "Der Markt von Rothenfeld"

    figuren = client.get("/api/fundus/figuren").json()["figuren"]
    namen = [(f["epoche"], f["name"]) for f in figuren]
    # Original bleibt bestehen, Kopie kommt zusaetzlich dazu.
    assert ("Regency", "Lady Amelia Hartwell") in namen
    assert ("Mittelalter", "Lady Amelia Hartwell") in namen
    assert len(figuren) == 3


def test_fundus_figur_kopieren_mit_neuem_namen(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.post("/api/fundus/figuren/kopieren", json={
        "epoche": "Regency", "name": "Lady Amelia Hartwell", "ziel_epoche": "Regency",
        "neuer_name": "Amelias Zwillingsschwester",
    })
    assert r.status_code == 201
    assert r.json()["name"] == "Amelias Zwillingsschwester"

    figuren = client.get("/api/fundus/figuren").json()["figuren"]
    assert any(f["name"] == "Amelias Zwillingsschwester" and f["epoche"] == "Regency" for f in figuren)
    assert any(f["name"] == "Lady Amelia Hartwell" and f["epoche"] == "Regency" for f in figuren)


def test_fundus_figur_kopieren_verweigert_kollision_im_ziel(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.post("/api/fundus/figuren/kopieren", json={
        "epoche": "Regency", "name": "Lady Amelia Hartwell", "ziel_epoche": "Regency",
    })
    assert r.status_code == 409


def test_fundus_figur_kopieren_unbekannte_quelle_gibt_404(client):
    _fundus_seed(client, _ZWEI_FIGUREN)
    r = client.post("/api/fundus/figuren/kopieren", json={
        "epoche": "Regency", "name": "Nicht Vorhanden", "ziel_epoche": "Mittelalter",
    })
    assert r.status_code == 404
