"""Tests fuer den Projekt-Abgleich Prod <-> lokal (app/core/projekt_sync.py,
app/api/sync.py). Die Gegenstelle wird durch eine Attrappe ersetzt, die die
Server-Endpunkte direkt mit den Einstellungen einer zweiten "Instanz"
aufruft (zwei echte Apps liessen sich im selben Prozess nicht trennen, weil
get_settings global ueberschrieben wird)."""
import io
import json
import tarfile

import pytest
from fastapi import HTTPException

from app.api import sync
from app.config import Settings
from app.core import projekt_sync as ps
from app.db import init_db
from app.schemas import Benutzer


def _projekt(wurzel, epoche_ordner, name, kapitel="Text eins", epoche="Regency"):
    pfad = wurzel / epoche_ordner / name
    (pfad / "projekt").mkdir(parents=True)
    (pfad / "projekt" / "geruest.md").write_text("# Titel\n", encoding="utf-8")
    (pfad / "projekt" / "kapitel_01.md").write_text(kapitel, encoding="utf-8")
    (pfad / ".epoche").write_text(epoche, encoding="utf-8")
    return pfad


# --- Kern -------------------------------------------------------------------

def test_hash_ignoriert_status_bak_und_sync_meta(tmp_path):
    p = _projekt(tmp_path, "E", "P")
    h1 = ps.inhalt_hash(p)
    (p / "projekt" / "automatik_status.json").write_text('{"laeuft": false, "x": 1}', encoding="utf-8")
    (p / "projekt" / "kapitel_01.md.bak").write_text("alt", encoding="utf-8")
    ps.projekt_id(p)
    assert ps.inhalt_hash(p) == h1
    (p / "projekt" / "kapitel_01.md").write_text("anders", encoding="utf-8")
    assert ps.inhalt_hash(p) != h1


def _info(hash_, basis, ts=100.0, pid="a"):
    return {"hash": hash_, "basis_hash": basis, "geaendert_ts": ts, "projekt_id": pid}


def test_vergleich_mit_gemeinsamer_basis():
    assert ps.vergleichen(_info("n", "b"), _info("b", "b"))["status"] == "lokal_neuer"
    assert ps.vergleichen(_info("b", "b"), _info("n", "b"))["status"] == "server_neuer"
    assert ps.vergleichen(_info("l", "b"), _info("s", "b"))["status"] == "abweichend"
    assert ps.vergleichen(_info("x", "b"), _info("x", "b"))["status"] == "gleich"
    assert not ps.vergleichen(_info("n", "b"), _info("b", "b"))["unsicher"]


def test_vergleich_ohne_basis_nutzt_zeitstempel_und_ist_unsicher():
    v = ps.vergleichen(_info("l", None, ts=500), _info("s", None, ts=100))
    assert (v["status"], v["unsicher"]) == ("lokal_neuer", True)
    v = ps.vergleichen(_info("l", None, ts=100), _info("s", None, ts=500))
    assert (v["status"], v["unsicher"]) == ("server_neuer", True)
    assert ps.vergleichen(_info("l", None, ts=100), _info("s", None, ts=101))["status"] == "abweichend"


def test_vergleich_nur_eine_seite():
    assert ps.vergleichen(_info("l", None), None)["status"] == "nur_lokal"
    assert ps.vergleichen(None, _info("s", None))["status"] == "nur_server"


def test_warnung_nur_bei_aelter_ueber_neuer():
    ok = {"status": "lokal_neuer"}
    assert ps.uebertragung_pruefen(ok, "hoch") is None
    assert ps.uebertragung_pruefen(ok, "runter") is not None
    assert ps.uebertragung_pruefen({"status": "server_neuer"}, "hoch") is not None
    assert ps.uebertragung_pruefen({"status": "server_neuer"}, "runter") is None
    assert ps.uebertragung_pruefen({"status": "abweichend"}, "hoch") is not None
    assert ps.uebertragung_pruefen({"status": "abweichend"}, "runter") is not None
    assert ps.uebertragung_pruefen({"status": "nur_lokal"}, "hoch") is None


def test_archiv_rundreise_spiegelt_und_loescht_ueberzaehliges(tmp_path):
    quelle = _projekt(tmp_path / "a", "E", "P", kapitel="neu")
    ziel = _projekt(tmp_path / "b", "E", "P", kapitel="alt")
    (ziel / "projekt" / "kapitel_02.md").write_text("ueberzaehlig", encoding="utf-8")
    (ziel / "projekt" / "x.md.bak").write_text("bleibt", encoding="utf-8")
    ps.archiv_entpacken(ps.archiv_erzeugen(quelle), ziel)
    assert (ziel / "projekt" / "kapitel_01.md").read_text(encoding="utf-8") == "neu"
    assert not (ziel / "projekt" / "kapitel_02.md").exists()
    assert (ziel / "projekt" / "x.md.bak").exists()  # instanz-lokal, nicht angefasst
    assert ps.inhalt_hash(ziel) == ps.inhalt_hash(quelle)


def test_archiv_mit_pfadtraversal_wird_abgelehnt(tmp_path):
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("../boese.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        ps.archiv_entpacken(puffer.getvalue(), tmp_path / "ziel")
    assert not (tmp_path / "boese.txt").exists()


def test_laufende_jobs_erkannt(tmp_path):
    p = _projekt(tmp_path, "E", "P")
    assert ps.laufende_jobs(p) == []
    (p / "projekt" / "automatik_status.json").write_text(json.dumps({"laeuft": True}), encoding="utf-8")
    assert ps.laufende_jobs(p) == ["automatik_status.json"]


# --- API mit zwei Instanzen ---------------------------------------------------

def _instanz(tmp_path, name):
    settings = Settings(projects_dir=tmp_path / name / "projects", database_path=tmp_path / name / "db.sqlite",
                        secret_key_path=tmp_path / name / ".key")
    settings.projects_dir.mkdir(parents=True)
    init_db(settings.database_path)
    db_benutzer = Benutzer(id=0, username="daniel", ist_admin=True)
    return settings, db_benutzer


class _Antwort:
    def __init__(self, daten=None, inhalt=b""):
        self._daten, self.content = daten, inhalt

    def json(self):
        return self._daten


class _FakeGegenstelle:
    """Ruft die Server-Endpunkte der Gegen-Instanz direkt auf."""
    basis = "fake://server"

    def __init__(self, settings, benutzer):
        self.settings, self.benutzer = settings, benutzer

    def get(self, pfad, **kw):
        if pfad == "/api/sync/projekte":
            return _Antwort(sync.projekte_mit_hash(self.settings, self.benutzer))
        if pfad == "/api/sync/archiv":
            return _Antwort(inhalt=sync.archiv_holen(kw["params"]["ordner"], self.settings, self.benutzer).body)
        raise AssertionError(pfad)

    def post(self, pfad, **kw):
        assert pfad == "/api/sync/archiv"
        import asyncio

        class _Req:
            async def body(_self):
                return kw["content"]

        p = kw["params"]
        antwort = asyncio.run(sync.archiv_einspielen(
            _Req(), projekt_id=p["projekt_id"], epoche=p.get("epoche"), name=p["name"], quell_hash=p["quell_hash"],
            ziel_ordner=p.get("ziel_ordner"), erwarteter_hash=p.get("erwarteter_hash"),
            settings=self.settings, benutzer=self.benutzer))
        return _Antwort(antwort)


@pytest.fixture
def zwei(tmp_path, monkeypatch):
    lokal, b_lokal = _instanz(tmp_path, "lokal")
    server, b_server = _instanz(tmp_path, "server")
    for s in (lokal, server):
        from app import db
        db.einstellung_unterordner_je_epoche_schreiben(s.database_path, True)
        db.sync_partner_schreiben(s.database_path, s.secret_key_path, url="http://x", username="u", password="p")
    monkeypatch.setattr(sync, "_Gegenstelle", lambda _partner: _FakeGegenstelle(server, b_server))
    return lokal, b_lokal, server, b_server


def _wurzel(settings, benutzer):
    return sync.projekte_wurzel(settings, benutzer.username)


def test_hochladen_neues_projekt_dann_gleich(zwei):
    lokal, bl, server, bs = zwei
    _projekt(_wurzel(lokal, bl), "Regency", "Meine-Story")
    zeilen = sync.vergleichen(lokal, bl)["zeilen"]
    assert zeilen[0]["status"] == "nur_lokal"

    ergebnis = sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/Meine-Story"), lokal, bl)
    assert ergebnis["uebertragen"] is True
    assert (_wurzel(server, bs) / "Regency" / "Meine-Story" / "projekt" / "kapitel_01.md").exists()
    assert sync.vergleichen(lokal, bl)["zeilen"][0]["status"] == "gleich"


def test_lokal_weitergeschrieben_ist_lokal_neuer_und_server_neuer_warnt(zwei):
    lokal, bl, server, bs = zwei
    p = _projekt(_wurzel(lokal, bl), "Regency", "S")
    sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)

    (p / "projekt" / "kapitel_02.md").write_text("lokal weitergeschrieben", encoding="utf-8")
    assert sync.vergleichen(lokal, bl)["zeilen"][0]["status"] == "lokal_neuer"

    # Herunterladen wuerde die neuere lokale Fassung ueberschreiben -> Warnung
    with pytest.raises(HTTPException) as e:
        sync.herunterladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)
    assert e.value.status_code == 409 and e.value.detail["art"] == "ueberschreiben"
    assert (p / "projekt" / "kapitel_02.md").exists()

    # Hochladen ist die richtige Richtung und geht ohne Rueckfrage
    sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)

    # Server wird weiterentwickelt: nun ist der Server neuer, Hochladen warnt
    (_wurzel(server, bs) / "Regency" / "S" / "projekt" / "kapitel_03.md").write_text("auf prod", encoding="utf-8")
    assert sync.vergleichen(lokal, bl)["zeilen"][0]["status"] == "server_neuer"
    with pytest.raises(HTTPException) as e:
        sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)
    assert e.value.detail["art"] == "ueberschreiben"


def test_abweichend_braucht_force_und_legt_sicherung_an(zwei):
    lokal, bl, server, bs = zwei
    p = _projekt(_wurzel(lokal, bl), "Regency", "S")
    sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)
    (p / "projekt" / "kapitel_01.md").write_text("lokal anders", encoding="utf-8")
    sp = _wurzel(server, bs) / "Regency" / "S"
    (sp / "projekt" / "kapitel_01.md").write_text("server anders", encoding="utf-8")

    assert sync.vergleichen(lokal, bl)["zeilen"][0]["status"] == "abweichend"
    with pytest.raises(HTTPException):
        sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)
    sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S", force=True), lokal, bl)
    assert (sp / "projekt" / "kapitel_01.md").read_text(encoding="utf-8") == "lokal anders"
    assert list((_wurzel(server, bs) / sync.SICHERUNGS_ORDNER).glob("S_*.tar.gz"))


def test_herunterladen_legt_projekt_im_epoche_unterordner_an(zwei):
    lokal, bl, server, bs = zwei
    _projekt(_wurzel(server, bs), "Burg-Schreckenstein", "Der-Neue", epoche="Burg Schreckenstein")
    zeile = sync.vergleichen(lokal, bl)["zeilen"][0]
    assert zeile["status"] == "nur_server"
    sync.herunterladen(sync.UebertragenAnfrage(ordner=zeile["server"]["ordner"]), lokal, bl)
    assert (_wurzel(lokal, bl) / "Burg-Schreckenstein" / "Der-Neue" / "projekt" / "kapitel_01.md").exists()
    assert sync.vergleichen(lokal, bl)["zeilen"][0]["status"] == "gleich"


def test_von_hand_kopiertes_projekt_wird_per_name_gepaart_und_ist_unsicher(zwei):
    lokal, bl, server, bs = zwei
    _projekt(_wurzel(server, bs), "Harry-Potter-Universum", "Gegenmittel", kapitel="prod")
    _projekt(_wurzel(lokal, bl), "Harry-Potter-Universum", "Gegenmittel", kapitel="lokal")
    zeilen = sync.vergleichen(lokal, bl)["zeilen"]
    assert len(zeilen) == 1 and zeilen[0]["unsicher"] is True


def test_laufender_job_blockiert_hochladen(zwei):
    lokal, bl, _server, _bs = zwei
    p = _projekt(_wurzel(lokal, bl), "Regency", "S")
    (p / "projekt" / "automatik_status.json").write_text('{"laeuft": true}', encoding="utf-8")
    with pytest.raises(HTTPException) as e:
        sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)
    assert e.value.status_code == 409


def test_lokal_aufraeumen_nur_wenn_server_alles_hat(zwei):
    lokal, bl, server, bs = zwei
    p = _projekt(_wurzel(lokal, bl), "Regency", "S")
    (_wurzel(lokal, bl) / "Regency" / "Fertig.pdf").write_text("pdf", encoding="utf-8")
    sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)

    (p / "projekt" / "kapitel_02.md").write_text("noch nicht auf dem Server", encoding="utf-8")
    with pytest.raises(HTTPException) as e:
        sync.lokal_entfernen_wenn_synchron(lokal, bl, "Regency/S", vorher_hochladen=False)
    assert e.value.detail["art"] == "nicht_synchron" and p.exists()

    sync.lokal_entfernen_wenn_synchron(lokal, bl, "Regency/S", vorher_hochladen=True)
    assert not p.exists()
    assert (_wurzel(lokal, bl) / "Regency" / "Fertig.pdf").exists()  # PDF daneben bleibt
    assert (_wurzel(server, bs) / "Regency" / "S" / "projekt" / "kapitel_02.md").exists()


def test_aufraeumen_vorgemerkt_auf_server_wird_lokal_sichtbar(zwei):
    lokal, bl, server, bs = zwei
    _projekt(_wurzel(lokal, bl), "Regency", "S")
    sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)
    assert sync.vergleichen(lokal, bl)["zeilen"][0]["aufraeumen_vorgemerkt"] is False

    sync.aufraeumen_vormerken(sync.AufraeumenVormerkenAnfrage(ordner="Regency/S"), server, bs)
    # Server wird beim Abschluss der Pruefung bereinigt/veraendert -> server_neuer, lokal unveraendert
    (_wurzel(server, bs) / "Regency" / "S" / "projekt" / "kapitel_01.md").write_text("korrigiert", encoding="utf-8")
    zeile = sync.vergleichen(lokal, bl)["zeilen"][0]
    assert zeile["status"] == "server_neuer" and zeile["aufraeumen_vorgemerkt"] is True
    sync.lokal_entfernen_wenn_synchron(lokal, bl, "Regency/S", vorher_hochladen=False)
    assert not (_wurzel(lokal, bl) / "Regency" / "S").exists()


def test_mp3_und_cover_log_werden_nicht_uebertragen_und_nie_geloescht(zwei):
    lokal, bl, server, bs = zwei
    p = _projekt(_wurzel(lokal, bl), "Regency", "S")
    (p / "hoerbuch.mp3").write_bytes(b"x" * 1000)
    (p / "projekt" / "cover_log").mkdir()
    (p / "projekt" / "cover_log" / "a.png").write_bytes(b"png")
    hash_vorher = ps.inhalt_hash(p)

    sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)
    ziel = _wurzel(server, bs) / "Regency" / "S"
    assert (ziel / "projekt" / "kapitel_01.md").exists()
    assert not (ziel / "hoerbuch.mp3").exists() and not (ziel / "projekt" / "cover_log").exists()

    # MP3 hinzufuegen/aendern aendert den Stand nicht
    (p / "neu.mp3").write_bytes(b"y")
    assert ps.inhalt_hash(p) == hash_vorher
    assert sync.vergleichen(lokal, bl)["zeilen"][0]["status"] == "gleich"

    # Server-Seite hat eigene MP3: Spiegeln beim Herunterladen laesst sie liegen
    (ziel / "server.mp3").write_bytes(b"z")
    (p / "projekt" / "kapitel_01.md").write_text("lokal neuer", encoding="utf-8")
    sync.hochladen(sync.UebertragenAnfrage(ordner="Regency/S"), lokal, bl)
    assert (ziel / "server.mp3").exists()

    # Lokal entfernen loescht Projektdateien, aber nicht MP3/cover_log
    antwort = sync.lokal_entfernen_wenn_synchron(lokal, bl, "Regency/S", vorher_hochladen=False)
    assert not (p / "projekt" / "kapitel_01.md").exists()
    assert (p / "hoerbuch.mp3").exists() and (p / "projekt" / "cover_log" / "a.png").exists()
    assert "bleiben" in antwort["nachricht"]
