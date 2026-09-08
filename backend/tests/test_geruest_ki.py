"""Tests fuer app/core/geruest_ki.py (reine Funktionen, kein LLM) plus ein
API-Test fuer app/api/geruest_ki.py mit gemocktem Ollama.

Muster wie test_analysator.py / test_automatik_api.py."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core import architekt as arch
from app.core import geruest as g
from app.core import geruest_ki as gk
from app.core.ollama_client import ChatEvent
from app.db import init_db
from app.main import app


def _antwort(kapitelzahl: int) -> dict:
    return {
        "titel_der_geschichte": "Der Ball",
        "zeitlinie_kurz": "Frühjahr 1815 über drei Monate.",
        "kapitel": [
            {
                "nummer": i,
                "titel": f"Kapitel {i}",
                "ort": "Landsitz",
                "zielwortzahl": 1500,
                "anwesende_figuren": ["Anna", "Lord B"],
                "vergangene_zeit": "" if i == 1 else "zwei Wochen später",
                "ereignis": "Es geschieht etwas Wichtiges an diesem Ort mit den Figuren. " * 2,
                "funktion_im_spannungsbogen": "Exposition" if i == 1 else "Steigende Handlung",
                "stand_der_liebeshandlung": f"Stand {i}.",
                "zustand_am_kapitelende": f"Haken {i}.",
            }
            for i in range(1, kapitelzahl + 1)
        ],
    }


def _rb(kapitelanzahl: int = 3) -> gk.Randbedingungen:
    return gk.Randbedingungen(
        praemisse="Zwei Menschen finden über einen gemeinsamen Wissensdurst zueinander.",
        kapitelanzahl=kapitelanzahl,
        setting="Regency England 1815",
        genre="Romantik",
        jahr="1815",
        jugendschutz_stufe="angedeutet",
        figuren=[gk.Figur(name="Anna", alter="22", rolle="Hauptfigur", kurzbeschreibung="klug, arm")],
    )


# --- antwort_validieren ----------------------------------------------------

def test_validieren_nummeriert_kapitel_fortlaufend_neu():
    roh = _antwort(3)
    roh["kapitel"][0]["nummer"] = 7  # falsche Modell-Nummer
    res = gk.antwort_validieren(json.dumps(roh), _rb(3))
    assert [k.nummer for k in res.antwort.kapitel] == [1, 2, 3]


def test_validieren_schneidet_zu_viele_kapitel_ab():
    res = gk.antwort_validieren(json.dumps(_antwort(5)), _rb(3))
    assert len(res.antwort.kapitel) == 3
    assert any("überzählige" in h for h in res.hinweise)


def test_validieren_meldet_zu_wenige_kapitel_ohne_zu_blockieren():
    res = gk.antwort_validieren(json.dumps(_antwort(2)), _rb(4))
    assert len(res.antwort.kapitel) == 2
    assert any("nur 2 von 4" in h for h in res.hinweise)


def test_validieren_uebernimmt_unbekannte_spannungsbogen_funktion_als_freitext():
    roh = _antwort(2)
    roh["kapitel"][1]["funktion_im_spannungsbogen"] = "Wendepunkt"
    res = gk.antwort_validieren(json.dumps(roh), _rb(2))
    assert res.antwort.kapitel[1].funktion_im_spannungsbogen == "Wendepunkt"
    assert any("Wendepunkt" in h for h in res.hinweise)


def test_validieren_wandelt_eigene_angabe_praefix_in_freitext():
    roh = _antwort(1)
    roh["kapitel"][0]["funktion_im_spannungsbogen"] = "Eigene Angabe: Rahmenhandlung"
    res = gk.antwort_validieren(json.dumps(roh), _rb(1))
    assert res.antwort.kapitel[0].funktion_im_spannungsbogen == "Rahmenhandlung"


def test_validieren_ersetzt_fehlende_zielwortzahl_durch_standard():
    roh = _antwort(1)
    roh["kapitel"][0]["zielwortzahl"] = 0
    rb = _rb(1)
    rb.zielwortzahl_pro_kapitel = 1800
    res = gk.antwort_validieren(json.dumps(roh), rb)
    assert res.antwort.kapitel[0].zielwortzahl == 1800


def test_validieren_wirft_bei_kaputtem_json():
    with pytest.raises(ValueError):
        gk.antwort_validieren("kein json", _rb(1))


def test_validieren_wirft_bei_leerer_kapitelliste():
    with pytest.raises(ValueError):
        gk.antwort_validieren(json.dumps({"titel_der_geschichte": "X", "kapitel": []}), _rb(1))


# --- Prompt / Schema / dynamische Optionen -----------------------------------

def test_system_prompt_ist_statisch_und_ohne_platzhalter():
    p = gk.system_prompt()
    assert "{{" not in p and "}}" not in p
    # zwei Aufrufe müssen exakt denselben String liefern (Prompt-Cache-Präfix)
    assert gk.system_prompt() == p


def test_antwort_schema_erzwingt_die_kapitelanzahl():
    s = gk.antwort_schema(5)
    assert s["properties"]["kapitel"]["minItems"] == 5
    assert s["properties"]["kapitel"]["maxItems"] == 5
    assert "titel_der_geschichte" in s["required"]


def test_dynamische_optionen_skalieren_mit_kapitelanzahl_und_sind_gedeckelt():
    assert gk.num_ctx_fuer(2) < gk.num_ctx_fuer(10)
    assert gk.num_ctx_fuer(30) == 16384
    assert gk.num_ctx_fuer(8) % 2048 == 0
    assert gk.num_predict_fuer(2) < gk.num_predict_fuer(10) <= 8192


# --- geruest_zusammenbauen ----------------------------------------------------

def test_zusammenbauen_besteht_kapitelplan_pruefen_und_liefert_alle_kapitel():
    rb = _rb(3)
    res = gk.antwort_validieren(json.dumps(_antwort(3)), rb)
    txt = gk.geruest_zusammenbauen(rb, res.antwort, "Regency")

    assert g.kapitelplan_pruefen(txt) == []
    assert set(g.kapitelplan_erkennen(txt).keys()) == {1, 2, 3}
    assert g.letztes_geplantes_kapitel(txt) == 3


def test_zusammenbauen_setzt_woertliche_pflicht_marker():
    rb = _rb(2)
    res = gk.antwort_validieren(json.dumps(_antwort(2)), rb)
    txt = gk.geruest_zusammenbauen(rb, res.antwort, "Regency")

    assert g.jahr_erkennen(txt) == "1815"
    assert g.jugendschutz_stufe_erkennen(txt) == "angedeutet"
    assert g.automatische_fortsetzung_aktiviert(txt) is False
    assert g.titel_erkennen(txt) == "Der Ball"


def test_zusammenbauen_ohne_jahr_hinterlaesst_platzhalter():
    rb = _rb(2)
    rb.jahr = ""
    res = gk.antwort_validieren(json.dumps(_antwort(2)), rb)
    txt = gk.geruest_zusammenbauen(rb, res.antwort, "Regency")
    assert "vierstellige Jahreszahl eintragen" in txt


def test_zusammenbauen_ausgangslage_wird_erkannt():
    rb = _rb(2)
    res = gk.antwort_validieren(json.dumps(_antwort(2)), rb)
    txt = gk.geruest_zusammenbauen(rb, res.antwort, "Regency")
    ausgangslage = arch.ausgangslage_erkennen(txt)
    assert ausgangslage and "Landsitz" in ausgangslage


def test_zusammenbauen_kapitelblock_format_wie_frontend_serializer():
    """Der Kapitelplan-Block muss dieselben eingerückten Feld-Labels tragen,
    die frontend/src/utils/kapitelplan.ts erwartet (sonst zerlegt der
    KapitelplanEditor die Karten nicht)."""
    rb = _rb(1)
    res = gk.antwort_validieren(json.dumps(_antwort(1)), rb)
    txt = gk.geruest_zusammenbauen(rb, res.antwort, "Regency")
    for label in ("Vergangene Zeit:", "Ort:", "Anwesende Figuren:", "Ereignis:",
                  "Zielwortzahl: ca.", "Funktion im Spannungsbogen:",
                  "Stand der Liebeshandlung:", "Zustand am Kapitelende:"):
        assert f"    *   {label}" in txt
    assert "*   **Kapitel eins: Kapitel 1**" in txt


# --- API: starten -> status -> abgeschlossen -----------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    app.dependency_overrides[get_settings] = lambda: settings

    async def _fake_chat_stream(base_url, rolle, system, user, ueberschreibe=None,
                                 timeout=3600.0, format=None, modell_override=None):
        antwort = json.dumps(_antwort(3))
        yield ChatEvent("content", text=antwort)
        yield ChatEvent("done", text=antwort, meta={})

    monkeypatch.setattr("app.api.geruest_ki.chat_stream", _fake_chat_stream)

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_api_starten_erzeugt_geruest_und_status_wird_fertig(client):
    ordner = client.post("/api/projects", json={"titel": "KiTest", "epoche": "Regency"}).json()["ordner"]

    r = client.post(
        f"/api/projects/{ordner}/geruest-ki/starten",
        json={"praemisse": "Zwei treffen sich.", "kapitelanzahl": 3, "setting": "Regency", "jahr": "1815"},
    )
    assert r.status_code == 202
    assert r.json() == {"gestartet": True}

    # BackgroundTasks laufen im TestClient nach dem Response synchron durch.
    status = client.get(f"/api/projects/{ordner}/geruest-ki/status").json()
    assert status["abgeschlossen"] is True
    assert status["fehler"] is None

    detail = client.get(f"/api/projects/{ordner}").json()
    assert detail["letztes_geplantes_kapitel"] == 3
    assert detail["jahr"] == "1815"


def test_api_status_ohne_lauf_ist_leer(client):
    ordner = client.post("/api/projects", json={"titel": "Leer", "epoche": "Regency"}).json()["ordner"]
    status = client.get(f"/api/projects/{ordner}/geruest-ki/status").json()
    assert status == {"laeuft": False, "phase": None, "log": [], "abgeschlossen": False, "fehler": None}


def test_api_eingabe_wird_gesichert_und_ist_wieder_abrufbar(client):
    ordner = client.post("/api/projects", json={"titel": "EingabeTest", "epoche": "Regency"}).json()["ordner"]

    assert client.get(f"/api/projects/{ordner}/geruest-ki/eingabe").json() is None

    client.post(
        f"/api/projects/{ordner}/geruest-ki/starten",
        json={"praemisse": "Zwei treffen sich im Nebel.", "kapitelanzahl": 4, "genre": "Krimi",
              "figuren": [{"name": "Mara", "alter": "30", "rolle": "Ermittlerin", "kurzbeschreibung": "zäh"}]},
    )

    gespeichert = client.get(f"/api/projects/{ordner}/geruest-ki/eingabe").json()
    assert gespeichert["praemisse"] == "Zwei treffen sich im Nebel."
    assert gespeichert["kapitelanzahl"] == 4
    assert gespeichert["genre"] == "Krimi"
    assert gespeichert["figuren"][0]["name"] == "Mara"
