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


def test_automatik_log_zeigt_fortschritt_waehrend_langsamem_streaming(client, projekt_mit_kapitelplan, monkeypatch):
    """Regression 2026-08-12: Auf einem langsamen KI-Ziel (CPU-Inferenz ohne
    dedizierte GPU) blieb das Automatik-Log zwischen "Autor schreibt..." und
    "Kapitel-Entwurf fertig" mehrere Minuten lang leer, weil Streaming-Chunks
    komplett verworfen wurden (siehe _automatik_log_zeile) - das sah aus wie
    ein Haenger, obwohl im Hintergrund aktiv Text erzeugt wurde. Mit
    AUTOMATIK_FORTSCHRITT_INTERVALL_SEK auf 0 gesetzt (jede Zeitspanne
    "ueberschreitet" die Schwelle) muss JEDER Content-Chunk eine Fortschritts-
    Zeile erzeugen oder aktualisieren - aber alle Chunks derselben laufenden
    Antwort teilen sich EINE Zeile (per Index ersetzt), statt das Log mit
    einer Zeile pro Chunk vollzuspammen."""
    monkeypatch.setattr(pipeline, "AUTOMATIK_FORTSCHRITT_INTERVALL_SEK", 0.0)

    async def _fake_chat_stream_mehrere_chunks(base_url, rolle, system, user, ueberschreibe=None,
                                                timeout=3600.0, format=None, modell_override=None):
        yield ChatEvent("content", text="Erster Teil. ")
        yield ChatEvent("content", text="Zweiter Teil. ")
        yield ChatEvent("content", text="Dritter Teil. " * 20)
        yield ChatEvent("done", text="Erster Teil. Zweiter Teil. " + "Dritter Teil. " * 20,
                         meta={"woerter": 44, "token_pro_sekunde": 5.1})

    monkeypatch.setattr(pipeline, "chat_stream", _fake_chat_stream_mehrere_chunks)

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={"max_durchlaeufe": 1})
    assert r.status_code == 200

    status = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    fortschritts_zeilen = [z for z in status["log"] if "schreibt noch" in z]
    # Genau EINE Fortschrittszeile fuer Kapitel 1 - nicht eine je Chunk -,
    # weil alle Chunks derselben Antwort dieselbe Zeile per Index ersetzen.
    # (Kapitel 2 erzeugt eine zweite, eigene Fortschrittszeile.)
    assert 1 <= len(fortschritts_zeilen) <= 2
    assert any("Wörter bisher" in z for z in fortschritts_zeilen)
    # Die finale, echte Wortzahl-Zeile muss weiterhin ganz normal erscheinen.
    assert any("Kapitel-Entwurf fertig" in z for z in status["log"])


def test_automatik_status_fuehrt_aktuellen_autor_text_live_mit(client, projekt_mit_kapitelplan, monkeypatch):
    """Das "Autor"-Fenster im Frontend (SchreibenPage.tsx) zeigt beim
    interaktiven Schreiben den per WebSocket gestreamten Text - im
    Automatikmodus gibt es keine WebSocket-Verbindung, also muss derselbe
    Text ueber aktueller_text() im Status-Objekt ankommen, sonst bleibt das
    Fenster ab dem ersten unbeaufsichtigten Kapitel fuer immer leer."""
    monkeypatch.setattr(pipeline, "AUTOMATIK_FORTSCHRITT_INTERVALL_SEK", 0.0)

    async def _fake_chat_stream_zwei_chunks(base_url, rolle, system, user, ueberschreibe=None,
                                             timeout=3600.0, format=None, modell_override=None):
        yield ChatEvent("content", text="Er trat ans Fenster. ")
        yield ChatEvent("content", text="Der Regen fiel unaufhörlich " * 10)
        yield ChatEvent("done", text="Er trat ans Fenster. " + "Der Regen fiel unaufhörlich " * 10,
                         meta={"woerter": 42, "token_pro_sekunde": 4.5})

    monkeypatch.setattr(pipeline, "chat_stream", _fake_chat_stream_zwei_chunks)

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={"max_durchlaeufe": 1})
    assert r.status_code == 200

    status = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    # Nach Abschluss von Kapitel 1 enthaelt aktueller_text den vollstaendigen,
    # zuletzt erzeugten Text (nicht leer, nicht nur den ersten Chunk).
    assert status["aktueller_text"] is not None
    assert "Er trat ans Fenster." in status["aktueller_text"]
    assert "Der Regen fiel unaufhörlich" in status["aktueller_text"]


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


def test_automatik_log_zeigt_pruefer_start_je_durchlauf(client, projekt_mit_kapitelplan):
    """Regression 2026-08-12: Phase 2 (Pruefen & Anwenden je Durchlauf) rief
    _pruefe_kapitel() bisher OHNE jede Log-Zeile auf - zwischen dem Ende
    eines Durchlaufs und der "N Korrektur(en) angewendet"-Zeile des naechsten
    herrschte komplette Stille, bis die vier parallelen Pruefer-Rollen
    fertig waren. Live gemeldet als vermeintlicher Haenger bei Kapitel 6,
    obwohl der Lauf kurz danach sauber abschloss. Jeder Durchlauf muss jetzt
    VOR dem Pruef-Aufruf eine eigene "Prüfer laufen..."-Zeile bekommen."""
    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={"max_durchlaeufe": 2})
    assert r.status_code == 200

    status = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    pruefer_start_zeilen = [z for z in status["log"] if "Prüfer laufen..." in z]
    # Mindestens ein "Prüfer laufen..." je geschriebenem Kapitel (Phase 2
    # startet fuer jedes Kapitel mit Durchlauf 1).
    assert len(pruefer_start_zeilen) >= status["gesamt_kapitel"]
    assert any("Kapitel 1, Durchlauf 1: Prüfer laufen..." in z for z in status["log"])


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


def test_automatik_start_haengt_verlauf_eintrag_an(client, projekt_mit_kapitelplan):
    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={"max_durchlaeufe": 1})
    assert r.status_code == 200

    verlauf = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/verlauf").json()
    assert len(verlauf) == 1
    assert verlauf[0]["status"] == "abgeschlossen"
    assert verlauf[0]["fortgesetzt"] is False
    assert verlauf[0]["dauer_sekunden"] >= 0


def test_automatik_fortsetzen_ueberspringt_bereits_geprueftes_kapitel(client, projekt_mit_kapitelplan, monkeypatch):
    """Reproduziert die Zwangstrennungs-Situation, die zu diesem Feature
    fuehrte: Kapitel 2 scheitert PERSISTENT (auch alle Retries, siehe
    AUTOMATIK_RETRY_VERSUCHE) im ERSTEN Pruef-Durchlauf der Phase 2
    (simulierter Verbindungsabbruch) - der Aufruf davor (waehrend Phase 1,
    direkt nach dem Schreiben von Kapitel 2, siehe _kapitel_schreiben_kern)
    laeuft absichtlich noch durch, damit beide Kapiteldateien wie im echten
    Vorfall bereits vollstaendig auf der Platte liegen, wenn der Fehler
    passiert. Ein Fortsetzen-Lauf darf Kapitel 1 NICHT erneut pruefen,
    sondern muss direkt bei Kapitel 2 weitermachen."""
    # Retry-Wartezeit auf 0 fuer den Test (sonst wuerde ein Fehlschlag echte
    # 5/10/15 Minuten Wartezeit ausloesen, siehe _automatik_mit_retry).
    monkeypatch.setattr(pipeline, "AUTOMATIK_RETRY_WARTEZEIT_SEK", 0)

    urspruengliche_pruefung = pipeline._pruefe_kapitel
    aufrufe: list[int] = []
    # Scheitert ab dem ZWEITEN Aufruf fuer Kapitel 2 (also ab Phase 2) und
    # bleibt es fuer den ganzen ersten Lauf inkl. aller Retries - bis der
    # Fortsetzen-Lauf die Verbindung "repariert".
    zustand = {"scheitert": True}

    async def _pruefung_die_bei_kapitel_2_ab_phase_2_scheitert(settings_, projekt, base_url, n, kapiteltext, zusatzhinweis=""):
        aufrufe.append(n)
        if n == 2 and zustand["scheitert"] and aufrufe.count(2) >= 2:
            raise pipeline.OllamaFehler("Simulierter Verbindungsabbruch")
        return await urspruengliche_pruefung(settings_, projekt, base_url, n, kapiteltext, zusatzhinweis)

    monkeypatch.setattr(pipeline, "_pruefe_kapitel", _pruefung_die_bei_kapitel_2_ab_phase_2_scheitert)

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={"max_durchlaeufe": 1})
    assert r.status_code == 200
    status = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    assert status["fehler"] is not None
    assert status["phase"] == "pruefen"
    assert status["aktuelles_kapitel"] == 2
    assert status["aktueller_durchlauf"] == 1
    assert status["fortsetzbar"] is True
    assert status["fehler_schritt"] == {
        "kapitel": 2, "phase": "pruefen", "durchlauf": 1, "fehler_nummer": "OllamaFehler",
    }
    # Phase 1 (Schreiben inkl. eingebauter Erstpruefung) fuer beide Kapitel,
    # dann Phase 2: Kapitel 1 Durchlauf 1 (ok), Kapitel 2 Durchlauf 1 - erster
    # Versuch plus AUTOMATIK_RETRY_VERSUCHE weitere, alle scheitern.
    assert aufrufe == [1, 2, 1] + [2] * (pipeline.AUTOMATIK_RETRY_VERSUCHE + 1)
    r1 = client.get(f"/api/projects/{projekt_mit_kapitelplan}/kapitel/1")
    r2 = client.get(f"/api/projects/{projekt_mit_kapitelplan}/kapitel/2")
    assert r1.status_code == 200 and r2.status_code == 200

    aufrufe.clear()
    zustand["scheitert"] = False  # "Server ist wieder erreichbar" fuer den Fortsetzen-Lauf.
    r2 = client.post(
        f"/api/projects/{projekt_mit_kapitelplan}/automatik/start",
        json={"max_durchlaeufe": 1, "fortsetzen": True},
    )
    assert r2.status_code == 200
    status2 = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    assert status2["abgeschlossen"] is True
    assert status2["fehler"] is None
    assert status2["fortsetzbar"] is False
    assert status2["fehler_schritt"] is None
    # Beim Fortsetzen kommt nur EIN weiterer Aufruf fuer Kapitel 2 dazu -
    # weder Kapitel 1 noch ein weiterer Schreib-Durchgang wird wiederholt.
    assert aufrufe == [2]

    verlauf = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/verlauf").json()
    assert [e["status"] for e in verlauf] == ["fehler", "abgeschlossen"]
    assert verlauf[1]["fortgesetzt"] is True


def test_automatik_wiederholt_bei_serverfehler_und_gibt_dann_auf(client, projekt_mit_kapitelplan, monkeypatch):
    """Kernverhalten des Vorfalls vom 2026-08-02 (stundenlange 502-
    Aussetzer, siehe Bedienungsanleitung): ein Ollama-Fehler beim Schreiben
    eines Kapitels darf nicht sofort zum Abbruch fuehren, sondern erst nach
    AUTOMATIK_RETRY_VERSUCHE weiteren, erfolglosen Versuchen. Erholt sich
    die Verbindung rechtzeitig (hier: beim letzten erlaubten Versuch),
    laeuft der Automatikmodus normal weiter, ohne dass status["fehler"]
    jemals gesetzt wird."""
    monkeypatch.setattr(pipeline, "AUTOMATIK_RETRY_WARTEZEIT_SEK", 0)

    urspruenglicher_kern = pipeline._kapitel_schreiben_kern
    versuche_kapitel_1 = {"n": 0}

    async def _kern_der_bei_kapitel_1_erst_beim_letzten_versuch_klappt(
        settings_, projekt_root_, base_url, n, zusatzhinweis, ssh_ziel_id, on_event,
    ):
        if n == 1:
            versuche_kapitel_1["n"] += 1
            if versuche_kapitel_1["n"] <= pipeline.AUTOMATIK_RETRY_VERSUCHE:
                raise pipeline.OllamaFehler("Ollama nicht erreichbar unter http://127.0.0.1:18321: HTTP 502")
        return await urspruenglicher_kern(settings_, projekt_root_, base_url, n, zusatzhinweis, ssh_ziel_id, on_event)

    monkeypatch.setattr(pipeline, "_kapitel_schreiben_kern", _kern_der_bei_kapitel_1_erst_beim_letzten_versuch_klappt)

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={"max_durchlaeufe": 1})
    assert r.status_code == 200

    status = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    assert status["fehler"] is None
    assert status["abgeschlossen"] is True
    assert versuche_kapitel_1["n"] == pipeline.AUTOMATIK_RETRY_VERSUCHE + 1
    # Ein Fehler-Log pro gescheitertem Versuch, plus eine Erfolgsmeldung fuer
    # die Wiederholung.
    fehler_zeilen = [z for z in status["log"] if z.startswith("Fehler bei Schreiben von Kapitel 1")]
    assert len(fehler_zeilen) == pipeline.AUTOMATIK_RETRY_VERSUCHE
    assert any("Wiederholung erfolgreich" in z for z in status["log"])


def test_automatik_stop_waehrend_durchlauf_wird_nicht_verloren(client, projekt_mit_kapitelplan, monkeypatch):
    """Regression: ein Stop-Klick WAEHREND eines laufenden Pruef-Durchlaufs
    (nicht nur zwischen zwei Kapiteln) darf nicht durch den naechsten
    status_schreiben()-Aufruf mit dem veralteten In-Memory-Wert von
    "stop_angefordert" wieder ueberschrieben werden - sonst wuerde ein
    mitten in Kapitel 1 geklickter Stop stillschweigend ignoriert und die
    Automatik wuerde bis zum Ende durchlaufen."""
    from app.core import automatik
    from app.services import projekt_pfad

    settings = app.dependency_overrides[get_settings]()
    projekt_root = projekt_pfad(settings, "daniel", projekt_mit_kapitelplan)

    aufrufe: list[int] = []

    async def _fake_pruefung(settings_, projekt, base_url, n, kapiteltext, zusatzhinweis=""):
        # Bewusst KEIN echter Aufruf/Dateischreiben (pd.schreib sichert eine
        # vorhandene Fassung ueber einen Sekunden-genauen Zeitstempel als
        # .bak - bei mehreren Aufrufen fuer dasselbe Kapitel INNERHALB
        # derselben Sekunde, wie hier durch die gemockten, verzoegerungsfreien
        # LLM-Aufrufe moeglich, wuerde das zu einem echten, aber fuer diesen
        # Test irrelevanten FileExistsError-Kollisionsrisiko fuehren).
        aufrufe.append(n)
        if n == 1 and aufrufe.count(1) == 2:
            status = automatik.status_lesen(projekt_root)
            status["stop_angefordert"] = True
            automatik.status_schreiben(projekt_root, status)
        return pipeline.BefundeAntwort(kapitel=n, erzeugt_am="x", jahr=None, befunde=[], quelltext_sha256=None)

    monkeypatch.setattr(pipeline, "_pruefe_kapitel", _fake_pruefung)
    # Erzwingt mehrere Durchlaeufe (sonst wuerde die Schleife nach Durchlauf 1
    # schon wegen "0 Korrekturen angewendet" von selbst enden, ohne dass der
    # Stop ueberhaupt noetig waere, um den Fehler zu zeigen).
    monkeypatch.setattr(
        automatik, "befunde_anwenden",
        lambda text, befunde: (text, [{"art": "angewendet", "grund": None, "fundstelle": "x", "vorschlag": "y"}]),
    )

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/start", json={"max_durchlaeufe": 5})
    assert r.status_code == 200

    status = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    assert status["abgeschlossen"] is False
    assert any("Gestoppt" in zeile and "Durchlauf 2" in zeile for zeile in status["log"])
    # Phase 1 schreibt zuerst BEIDE Kapitel (Aufrufe fuer 1 und 2), danach
    # beginnt Phase 2 bei Kapitel 1: Durchlauf 1 laeuft noch durch, Durchlauf
    # 2 wird durch den Stop verhindert - Kapitel 2s Pruef-Phase wird gar
    # nicht erst erreicht.
    assert aufrufe == [1, 2, 1]


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


def test_automatik_haelt_nach_checkpoint_bei_ungeloesten_funden_an(client, monkeypatch):
    """Vorfall "Das-Echo-der-Verpflichtung-Ein-Geheimnis-in-Winterbottom-
    Hall" (2026-08-10): Der Automatikmodus schrieb unbeaufsichtigt alle 6
    Kapitel durch, obwohl schon nach Kapitel 3 ein Grossteil der Pruefer-
    Funde uebersprungen wurde (u.a. ein echter Kontinuitaetsbruch). Ab
    AUTOMATIK_CHECKPOINT_INTERVALL (3) muss der Lauf anhalten, wenn das
    Protokoll ungeloeste ("uebersprungen") Funde enthaelt, statt blind mit
    Kapitel 4 weiterzumachen."""
    from app.schemas import Befund, BefundBeschreibung, BefundeAntwort

    r = client.post("/api/projects", json={"titel": "Checkpointtest", "epoche": "Regency"})
    ordner = r.json()["ordner"]
    geruest = (
        "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\n\n"
        "## Kapitelplan\n"
        "Kapitel 1: Ein Anfang. 5 Wörter.\n"
        "Kapitel 2: Weiter. 5 Wörter.\n"
        "Kapitel 3: Noch mehr. 5 Wörter.\n"
        "Kapitel 4: Ein Ende. 5 Wörter.\n"
    )
    client.put(f"/api/projects/{ordner}/geruest", json={"inhalt": geruest})

    async def _pruefung_mit_ungeloestem_fund(settings_, projekt, base_url, n, kapiteltext, zusatzhinweis=""):
        befund = Befund(
            id="b1", kategorien=["kontinuitaet"], fundstelle="irrelevant",
            beschreibungen=[BefundBeschreibung(quelle="kontinuitaet", text="Testbefund")],
            sicherheit=None, vorschlag=None, konflikt=False, gefunden=False,
            start=None, end=None,
        )
        return BefundeAntwort(kapitel=n, erzeugt_am="2026-01-01 10:00", jahr="1815", befunde=[befund])

    monkeypatch.setattr(pipeline, "_pruefe_kapitel", _pruefung_mit_ungeloestem_fund)

    r = client.post(f"/api/projects/{ordner}/automatik/start", json={"max_durchlaeufe": 1})
    assert r.status_code == 200
    status = client.get(f"/api/projects/{ordner}/automatik/status").json()

    assert status["abgeschlossen"] is False
    assert status["laeuft"] is False
    assert status["fehler"] is None
    assert status["fortsetzbar"] is True
    assert status["phase"] == "pruefen"
    assert status["aktuelles_kapitel"] == 4
    assert any("Angehalten nach Kapitel 3" in zeile for zeile in status["log"])
    # Kapitel 4 wurde in Phase 1 zwar schon geschrieben, aber noch nicht
    # geprueft - der "uebersprungen"-Protokolleintrag existiert nur fuer 1-3.
    kapitel_mit_befund = {e["kapitel"] for e in status["protokoll"] if e["art"] == "uebersprungen"}
    assert kapitel_mit_befund == {1, 2, 3}

    r4 = client.get(f"/api/projects/{ordner}/kapitel/4")
    assert r4.status_code == 200 and r4.text.strip()

    # "Fortsetzen" fuehrt den Lauf zu Ende, OHNE Kapitel 1-3 erneut zu pruefen.
    aufrufe: list[int] = []
    urspruengliche_fake = pipeline._pruefe_kapitel

    async def _zaehle_aufrufe(settings_, projekt, base_url, n, kapiteltext, zusatzhinweis=""):
        aufrufe.append(n)
        return await urspruengliche_fake(settings_, projekt, base_url, n, kapiteltext, zusatzhinweis)

    monkeypatch.setattr(pipeline, "_pruefe_kapitel", _zaehle_aufrufe)
    r2 = client.post(f"/api/projects/{ordner}/automatik/start", json={"max_durchlaeufe": 1, "fortsetzen": True})
    assert r2.status_code == 200
    status2 = client.get(f"/api/projects/{ordner}/automatik/status").json()
    assert status2["abgeschlossen"] is True
    assert aufrufe == [4]


def test_automatik_resten_bestaetigen_aendert_projektlisten_badge(client, projekt_mit_kapitelplan):
    """Nachdem die im Protokoll verbliebenen Reste (uebersprungene Funde)
    ueber den neuen Endpunkt quittiert wurden, soll die Projektliste nicht
    mehr "abgeschlossen_mit_resten" zeigen, obwohl das Protokoll selbst
    unveraendert bleibt (siehe app/core/automatik.py:reste_vorhanden)."""
    from app.core import automatik
    from app.services import projekt_pfad

    settings = app.dependency_overrides[get_settings]()
    projekt_root = projekt_pfad(settings, "daniel", projekt_mit_kapitelplan)
    status = automatik.status_lesen(projekt_root)
    status.update({
        "gestartet_am": "2026-01-01 10:00", "laeuft": False, "abgeschlossen": True, "fehler": None,
        "protokoll": [{"art": "uebersprungen", "grund": "konflikt"}],
    })
    automatik.status_schreiben(projekt_root, status)

    def zustand_in_projektliste() -> str | None:
        projekte = client.get("/api/projects").json()
        projekt = next(p for p in projekte if p["ordner"] == projekt_mit_kapitelplan)
        return projekt["automatik_zustand"]

    assert zustand_in_projektliste() == "abgeschlossen_mit_resten"
    vorher = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    assert vorher["resten_bestaetigt"] is False

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/resten-bestaetigen")
    assert r.status_code == 200
    assert r.json()["resten_bestaetigt"] is True

    nachher = client.get(f"/api/projects/{projekt_mit_kapitelplan}/automatik/status").json()
    assert nachher["resten_bestaetigt"] is True
    assert zustand_in_projektliste() == "abgeschlossen_sauber"


def test_automatik_resten_bestaetigen_waehrend_lauf_liefert_409(client, projekt_mit_kapitelplan):
    from app.core import automatik
    from app.services import projekt_pfad

    settings = app.dependency_overrides[get_settings]()
    projekt_root = projekt_pfad(settings, "daniel", projekt_mit_kapitelplan)
    status = automatik.status_lesen(projekt_root)
    status["laeuft"] = True
    automatik.status_schreiben(projekt_root, status)

    r = client.post(f"/api/projects/{projekt_mit_kapitelplan}/automatik/resten-bestaetigen")
    assert r.status_code == 409
