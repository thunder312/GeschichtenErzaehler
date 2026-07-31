import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core.ollama_client import ChatEvent
from app.db import init_db
from app.main import app
import app.api.pipeline as pipeline


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


KAPITELTEXT_ENTWURF = (
    "Dies ist ein automatisch geschriebenes Kapitel mit ausreichend vielen "
    "Wörtern, damit die Zielwortzahl locker erreicht wird und keine "
    "automatische Fortsetzung ausgelöst wird. " * 3
)


async def _fake_chat_stream(base_url, rolle, system, user, ueberschreibe=None,
                             timeout=3600.0, format=None, modell_override=None):
    yield ChatEvent("content", text=KAPITELTEXT_ENTWURF)
    yield ChatEvent("done", text=KAPITELTEXT_ENTWURF, meta={"woerter": 40, "token_pro_sekunde": 12.0})


async def _fake_sammle_antwort(base_url, rolle, system, user, format=None, modell_override=None):
    if format == "json":
        return '{"befunde": []}', {}
    return "Kurze Zusammenfassung des Kapitelstands.", {}


@pytest.fixture(autouse=True)
def _mock_ollama(monkeypatch):
    monkeypatch.setattr(pipeline, "chat_stream", _fake_chat_stream)
    monkeypatch.setattr(pipeline, "_sammle_antwort", _fake_sammle_antwort)


@pytest.fixture
def projekt_mit_kapitelplan(client):
    r = client.post("/api/projects", json={"titel": "Automatiktest", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    geruest = (
        "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\n\n"
        "## Kapitelplan\n"
        "Kapitel 1: Ein Anfang. 5 Wörter.\n"
        "Kapitel 2: Ein Ende. 5 Wörter.\n"
    )
    client.put(f"/api/projects/{ordner}/geruest", json={"inhalt": geruest})
    return ordner


def test_automatik_status_ohne_lauf_ist_leerzustand(client, projekt_mit_kapitelplan):
    r = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status")
    assert r.status_code == 200
    daten = r.json()
    assert daten["laeuft"] is False
    assert daten["abgeschlossen"] is False
    assert daten["log"] == []


def test_automatik_start_schreibt_alle_fehlenden_kapitel_und_schliesst_ab(client, projekt_mit_kapitelplan):
    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={"max_durchlaeufe": 2})
    assert r.status_code == 200
    assert r.json()["gestartet"] is True

    status = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    assert status["abgeschlossen"] is True
    assert status["laeuft"] is False
    assert status["fehler"] is None
    assert status["gesamt_kapitel"] == 2
    # Beide Kapitel wurden tatsaechlich als Datei gespeichert.
    r2 = client.get(f"/api/projects/{projekt_mit_kapitelplan}/kapitel/1")
    r3 = client.get(f"/api/projects/{projekt_mit_kapitelplan}/kapitel/2")
    assert r2.status_code == 200 and r2.text.strip()
    assert r3.status_code == 200 and r3.text.strip()


def test_automatik_start_verweigert_zweiten_gleichzeitigen_lauf(client, projekt_mit_kapitelplan, monkeypatch):
    # Simuliert einen bereits laufenden Job, ohne tatsaechlich einen zu
    # starten (der echte Lauf ist in Tests synchron/blockierend ueber
    # BackgroundTasks und waere hier schon fertig, bevor der zweite Aufruf
    # passiert - der Zustand wird deshalb direkt in der Statusdatei gesetzt).
    from app.core import automatik
    from app.services import projekt_pfad

    settings = app.dependency_overrides[get_settings]()
    projekt_root = projekt_pfad(settings, "daniel", projekt_mit_kapitelplan)
    status = automatik.status_lesen(projekt_root)
    status["laeuft"] = True
    automatik.status_schreiben(projekt_root, status)

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={})
    assert r.status_code == 409


def test_automatik_stop_setzt_flag_und_bricht_vor_naechstem_kapitel_ab(client, projekt_mit_kapitelplan, monkeypatch):
    """_automatik_lauf() setzt "stop_angefordert" beim Start selbst auf
    False zurueck (frischer Lauf) - ein vorab gesetztes Flag wuerde also
    sofort ueberschrieben. Realistischer Test deshalb: das Flag wird ALS
    SEITENEFFEKT nach dem Schreiben von Kapitel 1 gesetzt (simuliert einen
    User-Klick auf "Stoppen" waehrend Kapitel 1 lief) - die Schleife muss
    das vor Kapitel 2 bemerken und sauber abbrechen, Kapitel 1 bleibt aber
    gespeichert."""
    from app.core import automatik
    from app.services import projekt_pfad

    settings = app.dependency_overrides[get_settings]()
    projekt_root = projekt_pfad(settings, "daniel", projekt_mit_kapitelplan)

    urspruenglicher_kern = pipeline._kapitel_schreiben_kern
    aufrufe = {"n": 0}

    async def _kern_der_nach_erstem_kapitel_stoppt(settings_, projekt_root_, base_url, n, zusatzhinweis, ssh_ziel_id, on_event):
        ergebnis = await urspruenglicher_kern(settings_, projekt_root_, base_url, n, zusatzhinweis, ssh_ziel_id, on_event)
        aufrufe["n"] += 1
        if aufrufe["n"] == 1:
            status = automatik.status_lesen(projekt_root_)
            status["stop_angefordert"] = True
            automatik.status_schreiben(projekt_root_, status)
        return ergebnis

    monkeypatch.setattr(pipeline, "_kapitel_schreiben_kern", _kern_der_nach_erstem_kapitel_stoppt)

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={})
    assert r.status_code == 200

    status = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    assert status["abgeschlossen"] is False
    assert status["laeuft"] is False
    assert any("Gestoppt" in zeile and "Kapitel 2" in zeile for zeile in status["log"])
    # Kapitel 1 wurde noch geschrieben, Kapitel 2 nicht mehr.
    r1 = client.get(f"/api/projects/{projekt_mit_kapitelplan}/kapitel/1")
    r2 = client.get(f"/api/projects/{projekt_mit_kapitelplan}/kapitel/2")
    assert r1.status_code == 200 and r1.text.strip()
    assert r2.status_code == 404
