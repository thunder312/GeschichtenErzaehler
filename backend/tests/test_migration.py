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


def test_layout_migrieren_verschiebt_gesamt_md_aus_projekt_unterordner_und_benennt_um(tmp_path):
    settings = _settings(tmp_path)
    _altes_layout_anlegen(tmp_path)

    layout_migrieren(settings)

    neu = tmp_path / "projects" / settings.default_username / "Mittelalter" / "Meine-Geschichte"
    # Landet nicht nur eine Ebene hoeher, sondern heisst auch nach dem
    # Titel (= Ordnername), nicht mehr hartcodiert "gesamt.md".
    assert (neu / "Meine-Geschichte.md").exists()
    assert not (neu / "gesamt.md").exists()
    assert not (neu / "projekt" / "gesamt.md").exists()


def test_layout_migrieren_ist_idempotent(tmp_path):
    settings = _settings(tmp_path)
    _altes_layout_anlegen(tmp_path)

    layout_migrieren(settings)
    neu = tmp_path / "projects" / settings.default_username / "Mittelalter" / "Meine-Geschichte"
    inhalt_vorher = (neu / "Meine-Geschichte.md").read_text(encoding="utf-8")

    # Zweiter Aufruf darf nichts mehr veraendern und nicht fehlschlagen,
    # auch wenn der Ziel-Benutzerordner (und die Gesamtdatei dort) schon
    # existiert.
    layout_migrieren(settings)

    assert (neu / "Meine-Geschichte.md").read_text(encoding="utf-8") == inhalt_vorher
    assert (neu / "projekt" / "kapitel_01.md").exists()


def test_layout_migrieren_benennt_bereits_am_story_root_liegendes_gesamt_md_um(tmp_path):
    """Deckt den Fall ab, der bei Daniels echten Projekten vorlag: gesamt.md
    war durch eine FRUEHERE Migration schon im Story-Root, aber noch mit dem
    alten hartcodierten Namen - muss ebenfalls auf den Titel umbenannt
    werden, nicht nur der Umzug aus projekt/ (siehe vorherigen Test)."""
    settings = _settings(tmp_path)
    story_root = tmp_path / "projects" / settings.default_username / "Regency" / "Der-Sturm"
    (story_root / "projekt").mkdir(parents=True)
    (story_root / "projekt" / "kapitel_01.md").write_text("Text.", encoding="utf-8")
    (story_root / "gesamt.md").write_text("Der ganze Text.", encoding="utf-8")

    layout_migrieren(settings)

    assert (story_root / "Der-Sturm.md").read_text(encoding="utf-8") == "Der ganze Text."
    assert not (story_root / "gesamt.md").exists()


def test_layout_migrieren_ohne_bestehende_projekte_tut_nichts(tmp_path):
    settings = _settings(tmp_path)

    layout_migrieren(settings)

    assert not (tmp_path / "projects" / settings.default_username).exists()
