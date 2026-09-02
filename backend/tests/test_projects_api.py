import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def projekt(client):
    r = client.post("/api/projects", json={"titel": "Testprojekt", "epoche": "Regency"})
    assert r.status_code == 201
    return r.json()["ordner"]


def test_projektliste_zeigt_titel_und_kapitelanzahl_aus_projekt_unterordner(client, projekt, tmp_path):
    # Regression: die Listenansicht (GET /api/projects) suchte geruest.md
    # und kapitel_*.md faelschlich im AEUSSEREN Projektordner statt im
    # projekt/-Unterordner und zeigte deshalb immer Titel=None und
    # anzahl_kapitel=0, obwohl die Detailansicht (GET /api/projects/{ordner})
    # dieselben Dateien korrekt fand.
    antwort = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDer Turm im Nebel\n\n## Kapitelplan\n"
                   "Kapitel 1: Start. Zielwortzahl: 1000 Woerter.\n",
    })
    # Der abweichende Titel benennt den Ordner um (siehe
    # app/api/projects.py:geruest_schreiben) - fuer die weiteren Schritte
    # muss also der ZURUECKGEGEBENE neue Ordner verwendet werden, nicht mehr
    # der urspruengliche "projekt"-Fixture-Ordnername.
    aktueller_ordner = antwort.json()["neuer_ordner"] or projekt
    from app.core import projekt_dateien as pd
    projekt_pfad = tmp_path / "projects" / "daniel" / aktueller_ordner / "projekt"
    pd.schreib(pd.kapitel_datei(projekt_pfad, 1), "Ein Kapiteltext.")

    r = client.get("/api/projects")
    assert r.status_code == 200
    eintrag = next(p for p in r.json() if p["ordner"] == aktueller_ordner)
    assert eintrag["titel"] == "Der Turm im Nebel"
    assert eintrag["anzahl_kapitel"] == 1
    assert eintrag["letztes_geplantes_kapitel"] == 1


def test_projektliste_zeigt_automatik_zustand_none_ohne_lauf(client, projekt):
    eintrag = next(p for p in client.get("/api/projects").json() if p["ordner"] == projekt)
    assert eintrag["automatik_zustand"] is None


def test_projektliste_zeigt_automatik_zustand_mit_resten(client, projekt, tmp_path):
    from app.core import automatik

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    status = automatik.status_lesen(projekt_root)
    status.update({
        "gestartet_am": "2026-01-01 12:00", "laeuft": False, "fehler": None,
        "abgeschlossen": True,
        "protokoll": [{"art": "uebersprungen", "grund": "konflikt"}],
    })
    automatik.status_schreiben(projekt_root, status)

    eintrag = next(p for p in client.get("/api/projects").json() if p["ordner"] == projekt)
    assert eintrag["automatik_zustand"] == "abgeschlossen_mit_resten"


def test_projekt_loeschen_entfernt_den_kompletten_ordner(client, projekt, tmp_path):
    projekt_root = tmp_path / "projects" / "daniel" / projekt
    assert projekt_root.is_dir()

    r = client.delete(f"/api/projects/{projekt}")

    assert r.status_code == 204
    assert not projekt_root.exists()
    assert client.get("/api/projects").json() == []


def test_projekt_loeschen_unbekannter_ordner_gibt_404(client):
    r = client.delete("/api/projects/nicht-vorhanden")
    assert r.status_code == 404


def test_projekt_loeschen_blockiert_waehrend_automatik_laeuft(client, projekt, tmp_path):
    from app.core import automatik

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    status = automatik.status_lesen(projekt_root)
    status["laeuft"] = True
    automatik.status_schreiben(projekt_root, status)

    r = client.delete(f"/api/projects/{projekt}")

    assert r.status_code == 409
    assert projekt_root.is_dir()


def test_verbotsliste_lesen_und_schreiben(client, projekt):
    r = client.get(f"/api/projects/{projekt}")
    assert r.status_code == 200
    assert "Verbotsliste" in r.json()["verbotsliste"]

    r2 = client.put(f"/api/projects/{projekt}/verbotsliste", json={"inhalt": "# Verbotsliste\n\nNeuer Eintrag"})
    assert r2.status_code == 200

    r3 = client.get(f"/api/projects/{projekt}")
    assert r3.json()["verbotsliste"] == "# Verbotsliste\n\nNeuer Eintrag"


def test_personas_auflisten(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas")
    assert r.status_code == 200
    namen = r.json()
    assert "architekt" in namen
    assert "autor" in namen
    assert "chronist" in namen


def test_persona_lesen_und_schreiben(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas/autor")
    assert r.status_code == 200
    assert len(r.text) > 0

    r2 = client.put(f"/api/projects/{projekt}/personas/autor", json={"inhalt": "Neue Autor-Persona"})
    assert r2.status_code == 200

    r3 = client.get(f"/api/projects/{projekt}/personas/autor")
    assert r3.text == "Neue Autor-Persona"


def test_persona_unbekannter_name_wird_abgelehnt(client, projekt):
    r = client.get(f"/api/projects/{projekt}/personas/nicht_vorhanden")
    assert r.status_code == 404

    r2 = client.put(f"/api/projects/{projekt}/personas/nicht_vorhanden", json={"inhalt": "x"})
    assert r2.status_code == 404


def test_architekten_gespraech_ohne_abgeschlossenes_interview_404(client, projekt):
    r = client.get(f"/api/projects/{projekt}/architekten-gespraech")
    assert r.status_code == 404


def test_projekt_anlegen_ohne_titel_verwendet_platzhalter_neu(client):
    r = client.post("/api/projects", json={"titel": "", "epoche": "Regency"})
    assert r.status_code == 201
    assert r.json()["ordner"] == "neu"
    assert r.json()["titel"] is None


def test_projekt_anlegen_ohne_titel_zaehlt_bei_kollision_hoch(client):
    r1 = client.post("/api/projects", json={"titel": "", "epoche": "Regency"})
    r2 = client.post("/api/projects", json={"titel": "", "epoche": "Regency"})
    assert r1.json()["ordner"] == "neu"
    assert r2.json()["ordner"] == "neu-2"


def test_projekt_anlegen_mit_epoche_unterordner(client, tmp_path):
    client.put("/api/einstellungen", json={"unterordner_je_epoche": True})
    r = client.post("/api/projects", json={"titel": "Der Sturm", "epoche": "Regency"})
    assert r.status_code == 201
    daten = r.json()
    assert daten["ordner"] == "Regency/Der-Sturm"
    assert (tmp_path / "projects" / "daniel" / "Regency" / "Der-Sturm" / "projekt").is_dir()

    r2 = client.get(f"/api/projects/{daten['ordner']}")
    assert r2.status_code == 200

    r3 = client.get("/api/projects")
    assert any(p["ordner"] == "Regency/Der-Sturm" for p in r3.json())


def test_projekt_mit_epoche_unterordner_geruest_lesen_und_schreiben(client):
    client.put("/api/einstellungen", json={"unterordner_je_epoche": True})
    ordner = client.post("/api/projects", json={"titel": "Der Sturm", "epoche": "Regency"}).json()["ordner"]

    r = client.put(f"/api/projects/{ordner}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nDer Sturm\n",
    })
    assert r.status_code == 200

    r2 = client.get(f"/api/projects/{ordner}")
    assert "Der Sturm" in r2.json()["geruest"]


def test_projekt_anlegen_mit_zweiter_epoche_setzt_zeitsprung_marker(client, tmp_path):
    r = client.post("/api/projects", json={
        "titel": "Der Sprung durch die Zeit", "epoche": "Mittelalter", "zweite_epoche": "Zukunft",
    })
    assert r.status_code == 201
    daten = r.json()
    assert daten["epoche"] == "Mittelalter"
    assert daten["zweite_epoche"] == "Zukunft"

    r2 = client.get(f"/api/projects/{daten['ordner']}")
    assert r2.json()["epoche"] == "Mittelalter"
    assert r2.json()["zweite_epoche"] == "Zukunft"

    personas = tmp_path / "projects" / "daniel" / daten["ordner"] / "personas"
    for datei in ("architekt.txt", "autor.txt", "pruefer_anachronismus.txt"):
        inhalt = (personas / datei).read_text(encoding="utf-8")
        assert "ZEITSPRUNG" in inhalt
        assert "Zukunft" in inhalt

    verbotsliste = (tmp_path / "projects" / "daniel" / daten["ordner"] / "projekt" / "verbotsliste.md").read_text(
        encoding="utf-8",
    )
    assert "Epoche: Mittelalter" in verbotsliste
    assert "Epoche: Zukunft" in verbotsliste


def test_projekt_anlegen_ohne_zweite_epoche_hat_keinen_zeitsprung_marker(client, projekt, tmp_path):
    assert not (tmp_path / "projects" / "daniel" / projekt / ".epoche_zweite").exists()
    r = client.get(f"/api/projects/{projekt}")
    assert r.json()["zweite_epoche"] is None


def test_projekt_anlegen_mit_gleicher_zweiter_epoche_wird_abgelehnt(client):
    r = client.post("/api/projects", json={
        "titel": "X", "epoche": "Regency", "zweite_epoche": "Regency",
    })
    assert r.status_code == 422


def test_projekt_anlegen_mit_unbekannter_zweiter_epoche_gibt_404(client):
    r = client.post("/api/projects", json={
        "titel": "X", "epoche": "Regency", "zweite_epoche": "Nicht-Vorhanden",
    })
    assert r.status_code == 404


def test_projekt_ohne_epoche_unterordner_bleibt_flach(client, tmp_path):
    r = client.post("/api/projects", json={"titel": "Der Sturm", "epoche": "Regency"})
    assert r.json()["ordner"] == "Der-Sturm"
    assert (tmp_path / "projects" / "daniel" / "Der-Sturm" / "projekt").is_dir()


def test_projekt_bereinigen_loescht_bak_und_alte_staende(client, projekt, tmp_path):
    from app.core import projekt_dateien as pd

    projekt_pfad = tmp_path / "projects" / "daniel" / projekt / "projekt"
    pd.schreib(pd.stand_datei(projekt_pfad, 0), "Stand 0")
    pd.schreib(pd.stand_datei(projekt_pfad, 1), "Stand 1")
    (projekt_pfad / "geruest.md.1234567890.bak").write_text("alte Fassung", encoding="utf-8")

    r = client.post(f"/api/projects/{projekt}/bereinigen")

    assert r.status_code == 200
    assert r.json() == {"geloeschte_bak": 1, "geloeschte_stand": 1}
    assert not (projekt_pfad / "stand_00.md").exists()
    assert (projekt_pfad / "stand_01.md").exists()
    assert not list(projekt_pfad.glob("*.bak"))


def test_projekt_bereinigen_blockiert_waehrend_automatik_laeuft(client, projekt, tmp_path):
    from app.core import automatik

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    status = automatik.status_lesen(projekt_root)
    status["laeuft"] = True
    automatik.status_schreiben(projekt_root, status)

    r = client.post(f"/api/projects/{projekt}/bereinigen")

    assert r.status_code == 409


def test_geruest_schreiben_aktualisiert_stand_00_aus_ausgangslage(client, projekt, tmp_path):
    r = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n"
                   "## Ausgangslage vor Kapitel eins\n"
                   "### Zeit\n*   Datum/Jahreszeit: Sommer, Juli.\n",
    })

    assert r.status_code == 200
    assert r.json()["stand_00_aktualisiert"] is True
    stand_00 = tmp_path / "projects" / "daniel" / projekt / "projekt" / "stand_00.md"
    assert "Sommer, Juli" in stand_00.read_text(encoding="utf-8")


def test_geruest_schreiben_ueberschreibt_stand_00_bei_geaenderter_ausgangslage(client, projekt, tmp_path):
    # Regression: nach "Neu schreiben" enthielt stand_00.md noch die
    # Ausgangslage des URSPRUENGLICHEN Projekts (siehe
    # projekt_fuer_neuschreiben_duplizieren) - eine spaetere Korrektur der
    # Ausgangslage im Geruest-Editor (z.B. Jahreszeit Herbst->Sommer) wurde
    # bisher NICHT nach stand_00.md uebernommen, wodurch der Autor beim
    # Schreiben von Kapitel eins zwei widerspruechliche Quellen bekam und im
    # Zweifel die alte (stand_00.md) uebernahm.
    client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n"
                   "## Ausgangslage vor Kapitel eins\n"
                   "### Zeit\n*   Datum/Jahreszeit: Herbst, kühl.\n",
    })

    r = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n"
                   "## Ausgangslage vor Kapitel eins\n"
                   "### Zeit\n*   Datum/Jahreszeit: Sommer, warm.\n",
    })

    assert r.json()["stand_00_aktualisiert"] is True
    stand_00 = tmp_path / "projects" / "daniel" / projekt / "projekt" / "stand_00.md"
    inhalt = stand_00.read_text(encoding="utf-8")
    assert "Sommer, warm" in inhalt
    assert "Herbst" not in inhalt


def test_geruest_schreiben_ohne_ausgangslage_laesst_bestehendes_stand_00_unangetastet(client, projekt, tmp_path):
    projekt_pfad = tmp_path / "projects" / "daniel" / projekt / "projekt"
    from app.core import projekt_dateien as pd
    pd.schreib(pd.stand_datei(projekt_pfad, 0), "# STAND VOR KAPITEL EINS\n\nUnveraendert")

    r = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n## Konflikt\nKein Ausgangslage-Abschnitt.\n",
    })

    assert r.json()["stand_00_aktualisiert"] is False
    assert "Unveraendert" in (projekt_pfad / "stand_00.md").read_text(encoding="utf-8")


def test_geruest_schreiben_lehnt_kapitelplan_ohne_zielwortzahl_ab(client, projekt, tmp_path):
    r = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n"
                   "## Kapitelplan\nKapitel 1: Ankunft.\nKapitel 2: Ende. Zielwortzahl: 1.000 Woerter.\n",
    })

    assert r.status_code == 400
    assert "Kapitel 1" in r.json()["detail"]
    assert "Zielwortzahl" in r.json()["detail"]
    # Es darf gar nichts geschrieben worden sein - kein geruest.md vorhanden.
    assert not (tmp_path / "projects" / "daniel" / projekt / "projekt" / "geruest.md").exists()


def test_geruest_schreiben_lehnt_doppelte_kapitelnummer_ab(client, projekt, tmp_path):
    r = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n"
                   "## Kapitelplan\nKapitel 1: Ankunft. Zielwortzahl: 1.000 Woerter.\n"
                   "Kapitel 1: Nochmal. Zielwortzahl: 1.200 Woerter.\n",
    })

    assert r.status_code == 400
    assert "mehrfach" in r.json()["detail"]


def test_geruest_schreiben_ueberschreibt_bestehendes_geruest_nicht_bei_fehler(client, projekt, tmp_path):
    projekt_pfad = tmp_path / "projects" / "daniel" / projekt / "projekt"
    client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n"
                   "## Kapitelplan\nKapitel 1: Ankunft. Zielwortzahl: 1.000 Woerter.\n",
    })

    r = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n## Kapitelplan\nKapitel 1: Ankunft ohne Ziel.\n",
    })

    assert r.status_code == 400
    assert "Zielwortzahl: 1.000" in (projekt_pfad / "geruest.md").read_text(encoding="utf-8")


def test_geruest_schreiben_erlaubt_kapitelplan_mit_zielwortzahl(client, projekt):
    r = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n"
                   "## Kapitelplan\nKapitel 1: Ankunft. Zielwortzahl: 1.000 Woerter.\n",
    })

    assert r.status_code == 200


def test_geruest_schreiben_ohne_kapitelplan_abschnitt_bleibt_erlaubt(client, projekt):
    r = client.put(f"/api/projects/{projekt}/geruest", json={
        "inhalt": "# STORY-GERUEST\n\n## Titel\nTestprojekt\n\n## Konflikt\nNoch ohne Kapitelplan.\n",
    })

    assert r.status_code == 200


def test_projekt_epoche_aendern_setzt_marker_ohne_unterordner_je_epoche(client, projekt, tmp_path):
    # Standard-Einstellung (siehe db.einstellung_unterordner_je_epoche_lesen)
    # - der Projektordner bleibt physisch an Ort und Stelle, nur der
    # ".epoche"-Marker aendert sich.
    r = client.put(f"/api/projects/{projekt}/epoche", json={"epoche": "Mittelalter"})
    assert r.status_code == 200
    body = r.json()
    assert body["epoche"] == "Mittelalter"
    assert body["ordner"] == projekt

    marker = tmp_path / "projects" / "daniel" / projekt / ".epoche"
    assert marker.read_text(encoding="utf-8") == "Mittelalter"


def test_projekt_epoche_aendern_unbekannte_epoche_gibt_404(client, projekt):
    r = client.put(f"/api/projects/{projekt}/epoche", json={"epoche": "Nicht-Vorhanden"})
    assert r.status_code == 404


def test_projekt_epoche_aendern_blockiert_waehrend_automatik_laeuft(client, projekt, tmp_path):
    from app.core import automatik

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    status = automatik.status_lesen(projekt_root)
    status["laeuft"] = True
    automatik.status_schreiben(projekt_root, status)

    r = client.put(f"/api/projects/{projekt}/epoche", json={"epoche": "Mittelalter"})

    assert r.status_code == 409
    assert (projekt_root / ".epoche").read_text(encoding="utf-8") == "Regency"


def test_projekt_epoche_aendern_verschiebt_ordner_wenn_unterordner_je_epoche_aktiv(client, projekt, tmp_path):
    from app import db

    settings = client.app.dependency_overrides[get_settings]()
    db.einstellung_unterordner_je_epoche_schreiben(settings.database_path, True)

    r = client.put(f"/api/projects/{projekt}/epoche", json={"epoche": "Mittelalter"})
    assert r.status_code == 200
    body = r.json()
    assert body["ordner"] == f"Mittelalter/{projekt}"

    alter_pfad = tmp_path / "projects" / "daniel" / projekt
    neuer_pfad = tmp_path / "projects" / "daniel" / "Mittelalter" / projekt
    assert not alter_pfad.exists()
    assert neuer_pfad.is_dir()
    assert (neuer_pfad / ".epoche").read_text(encoding="utf-8") == "Mittelalter"

    # Ueber die Liste weiterhin auffindbar, jetzt unter dem neuen Pfad.
    liste = client.get("/api/projects").json()
    assert any(p["ordner"] == f"Mittelalter/{projekt}" and p["epoche"] == "Mittelalter" for p in liste)


def _befunde_json_schreiben(projekt_root, n, befunde):
    from app.core import projekt_dateien as pd

    inhalt = {
        "kapitel": n, "erzeugt_am": "2026-01-01 12:00", "jahr": "1811",
        "befunde": befunde, "quelltext_sha256": None,
    }
    import json
    pd.befunde_datei(projekt_root / "projekt", n).write_text(
        json.dumps(inhalt, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def _beispiel_befund(id_="b1", kategorien=None, fundstelle="Der Zauberer reiste nach London"):
    return {
        "id": id_, "kategorien": kategorien or ["stimmigkeit"], "fundstelle": fundstelle,
        "beschreibungen": [{"quelle": "stimmigkeit", "text": "Ort weicht vom Kanon ab"}],
        "sicherheit": "mittel", "vorschlag": "Der Zauberer reiste nach Berlin",
        "konflikt": False, "konflikt_vorschlaege": None, "gefunden": True,
        "start": 0, "end": len("Der Zauberer reiste nach London"),
    }


def test_befund_ablehnen_entfernt_ihn_sofort_und_dauerhaft(client, projekt, tmp_path):
    projekt_root = tmp_path / "projects" / "daniel" / projekt
    _befunde_json_schreiben(projekt_root, 1, [_beispiel_befund()])

    r = client.post(f"/api/projects/{projekt}/befunde/1/ablehnen", json={"befund_id": "b1"})
    assert r.status_code == 200
    assert r.json() == {"abgelehnt": True}

    # Sofort aus der gespeicherten Datei entfernt - ein simpler Reload zeigt
    # den Fund nicht wieder.
    gelesen = client.get(f"/api/projects/{projekt}/befunde/1").json()
    assert gelesen["befunde"] == []

    # Und projektweit als dauerhaft abgelehnt vermerkt, damit ein kuenftiger
    # /pruefen-Lauf ihn nicht erneut meldet.
    from app.core import befunde_ablehnung
    abgelehnte = befunde_ablehnung.lesen(projekt_root / "projekt")
    assert any(e["kategorie"] == "stimmigkeit" for e in abgelehnte)


def test_befund_ablehnen_unbekannte_id_gibt_404(client, projekt, tmp_path):
    projekt_root = tmp_path / "projects" / "daniel" / projekt
    _befunde_json_schreiben(projekt_root, 1, [_beispiel_befund()])

    r = client.post(f"/api/projects/{projekt}/befunde/1/ablehnen", json={"befund_id": "b-nicht-vorhanden"})
    assert r.status_code == 404


def test_befund_ablehnen_ohne_befunde_datei_gibt_404(client, projekt):
    r = client.post(f"/api/projects/{projekt}/befunde/1/ablehnen", json={"befund_id": "b1"})
    assert r.status_code == 404


def test_befund_uebernehmen_wendet_vorschlag_an_und_speichert_kapitel(client, projekt, tmp_path):
    """Mobil-Ansicht (MobilPage.tsx): "Übernehmen" ohne Monaco-Editor - der
    Server splict den Vorschlag direkt in kapitel_NN.md."""
    from app.core import projekt_dateien as pd

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    text = "Der Zauberer reiste nach London und traf einen Freund."
    pd.schreib(pd.kapitel_datei(projekt_root / "projekt", 1), text)
    _befunde_json_schreiben(projekt_root, 1, [_beispiel_befund()])

    r = client.post(f"/api/projects/{projekt}/befunde/1/uebernehmen", json={"befund_id": "b1"})
    assert r.status_code == 200
    assert r.json()["befunde"] == []

    neuer_text = client.get(f"/api/projects/{projekt}/kapitel/1").text
    assert neuer_text.strip() == "Der Zauberer reiste nach Berlin und traf einen Freund."


def test_befund_uebernehmen_mit_override_nutzt_abgeaenderten_text(client, projekt, tmp_path):
    """Button "kleine Verbesserung": vorschlag_override ersetzt den
    urspruenglichen Pruefer-Vorschlag vor dem Übernehmen."""
    from app.core import projekt_dateien as pd

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    text = "Der Zauberer reiste nach London."
    pd.schreib(pd.kapitel_datei(projekt_root / "projekt", 1), text)
    _befunde_json_schreiben(projekt_root, 1, [_beispiel_befund()])

    r = client.post(
        f"/api/projects/{projekt}/befunde/1/uebernehmen",
        json={"befund_id": "b1", "vorschlag_override": "Der Zauberer reiste nach Wien"},
    )
    assert r.status_code == 200

    neuer_text = client.get(f"/api/projects/{projekt}/kapitel/1").text
    assert neuer_text.strip() == "Der Zauberer reiste nach Wien."


def test_befund_uebernehmen_verankert_uebrige_offene_funde_neu(client, projekt, tmp_path):
    """Live-Fund 2026-09-02: ein NICHT uebernommener Fund, der im Text HINTER
    dem gerade uebernommenen liegt, muss danach eine aktualisierte Position
    haben - sonst verschwindet er im Frontend als "verwaist"."""
    from app.core import projekt_dateien as pd

    projekt_root = tmp_path / "projects" / "daniel" / projekt
    text = "Er ging zu Fuss durch den Wald und traf einen unsicheren Freund."
    pd.schreib(pd.kapitel_datei(projekt_root / "projekt", 1), text)
    befund_anwendbar = _beispiel_befund(id_="b1", fundstelle="Fuss")
    befund_anwendbar["vorschlag"] = "Fuß"
    befund_anwendbar["start"] = text.index("Fuss")
    befund_anwendbar["end"] = text.index("Fuss") + len("Fuss")
    fundstelle_offen = "unsicheren Freund"
    befund_offen = _beispiel_befund(id_="b2", fundstelle=fundstelle_offen)
    befund_offen["vorschlag"] = None
    befund_offen["start"] = text.index(fundstelle_offen)
    befund_offen["end"] = text.index(fundstelle_offen) + len(fundstelle_offen)
    _befunde_json_schreiben(projekt_root, 1, [befund_anwendbar, befund_offen])

    r = client.post(f"/api/projects/{projekt}/befunde/1/uebernehmen", json={"befund_id": "b1"})
    assert r.status_code == 200
    verbleibend = r.json()["befunde"]
    assert len(verbleibend) == 1
    assert verbleibend[0]["id"] == "b2"
    assert verbleibend[0]["gefunden"] is True

    neuer_text = client.get(f"/api/projects/{projekt}/kapitel/1").text
    assert neuer_text[verbleibend[0]["start"]:verbleibend[0]["end"]] == fundstelle_offen


def test_befund_uebernehmen_unbekannte_id_gibt_404(client, projekt, tmp_path):
    projekt_root = tmp_path / "projects" / "daniel" / projekt
    pd_kapitel_text_schreiben(projekt_root, 1, "Ein Kapiteltext.")
    _befunde_json_schreiben(projekt_root, 1, [_beispiel_befund()])

    r = client.post(f"/api/projects/{projekt}/befunde/1/uebernehmen", json={"befund_id": "unbekannt"})
    assert r.status_code == 404


def test_befund_uebernehmen_ohne_vorschlag_gibt_400(client, projekt, tmp_path):
    projekt_root = tmp_path / "projects" / "daniel" / projekt
    pd_kapitel_text_schreiben(projekt_root, 1, "Der Zauberer reiste nach London.")
    befund = _beispiel_befund()
    befund["vorschlag"] = None
    _befunde_json_schreiben(projekt_root, 1, [befund])

    r = client.post(f"/api/projects/{projekt}/befunde/1/uebernehmen", json={"befund_id": "b1"})
    assert r.status_code == 400


def test_befund_uebernehmen_textstelle_nicht_gefunden_gibt_409(client, projekt, tmp_path):
    projekt_root = tmp_path / "projects" / "daniel" / projekt
    # Kapiteltext enthaelt die Fundstelle des Befunds gar nicht (z.B. schon
    # anderweitig veraendert).
    pd_kapitel_text_schreiben(projekt_root, 1, "Ganz anderer Text.")
    _befunde_json_schreiben(projekt_root, 1, [_beispiel_befund()])

    r = client.post(f"/api/projects/{projekt}/befunde/1/uebernehmen", json={"befund_id": "b1"})
    assert r.status_code == 409


def pd_kapitel_text_schreiben(projekt_root, n, text):
    from app.core import projekt_dateien as pd

    pd.schreib(pd.kapitel_datei(projekt_root / "projekt", n), text)
