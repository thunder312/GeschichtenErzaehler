from app.config import Settings
from app.db import init_db
from app.migration import layout_migrieren


def _settings(tmp_path):
    s = Settings(
        projects_dir=tmp_path / "projects",
        database_path=tmp_path / "novelle_gui.db",
        secret_key_path=tmp_path / ".secret_key",
    )
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    init_db(s.database_path)
    return s


def _altes_layout_anlegen(tmp_path):
    # Epoche-verschachteltes Projekt (aeltere "Unterordner je Epoche"-Struktur)
    projekt = tmp_path / "projects" / "Mittelalter" / "Meine-Geschichte" / "projekt"
    projekt.mkdir(parents=True)
    (projekt / "kapitel_01.md").write_text("Kapitel eins.", encoding="utf-8")
    (projekt / "gesamt.md").write_text("Kapitel eins.", encoding="utf-8")

    # Flaches Projekt direkt an der Wurzel (keine Epoche-Unterordner-Einstellung)
    flach = tmp_path / "projects" / "Flaches-Projekt" / "projekt"
    flach.mkdir(parents=True)
    (flach / "kapitel_01.md").write_text("Text.", encoding="utf-8")


def test_layout_migrieren_verschiebt_bestehende_projekte_unter_default_username(tmp_path):
    settings = _settings(tmp_path)
    _altes_layout_anlegen(tmp_path)

    layout_migrieren(settings)

    neu = tmp_path / "projects" / settings.default_username
    assert (neu / "Mittelalter" / "Meine-Geschichte" / "projekt" / "kapitel_01.md").exists()
    assert (neu / "Flaches-Projekt" / "projekt" / "kapitel_01.md").exists()
    # Alte Pfade an der Wurzel existieren nicht mehr.
    assert not (tmp_path / "projects" / "Mittelalter").exists()
    assert not (tmp_path / "projects" / "Flaches-Projekt").exists()


def test_layout_migrieren_verschiebt_gesamt_md_aus_projekt_unterordner(tmp_path):
    settings = _settings(tmp_path)
    _altes_layout_anlegen(tmp_path)

    layout_migrieren(settings)

    neu = tmp_path / "projects" / settings.default_username / "Mittelalter" / "Meine-Geschichte"
    assert (neu / "gesamt.md").exists()
    assert not (neu / "projekt" / "gesamt.md").exists()


def test_layout_migrieren_ist_idempotent(tmp_path):
    settings = _settings(tmp_path)
    _altes_layout_anlegen(tmp_path)

    layout_migrieren(settings)
    neu = tmp_path / "projects" / settings.default_username / "Mittelalter" / "Meine-Geschichte"
    inhalt_vorher = (neu / "gesamt.md").read_text(encoding="utf-8")

    # Zweiter Aufruf darf nichts mehr veraendern und nicht fehlschlagen,
    # auch wenn der Ziel-Benutzerordner (und gesamt.md dort) schon existiert.
    layout_migrieren(settings)

    assert (neu / "gesamt.md").read_text(encoding="utf-8") == inhalt_vorher
    assert (neu / "projekt" / "kapitel_01.md").exists()


def test_layout_migrieren_ohne_bestehende_projekte_tut_nichts(tmp_path):
    settings = _settings(tmp_path)

    layout_migrieren(settings)

    assert not (tmp_path / "projects" / settings.default_username).exists()
