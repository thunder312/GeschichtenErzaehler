from pathlib import Path

from app.core import geruest as g
from app.core import projekt_dateien as pd


def test_projektordner_umbenennen_nach_titel(tmp_path):
    projekt_root = tmp_path / "Rohtitel"
    (projekt_root / "projekt").mkdir(parents=True)
    geruest = "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n"

    neuer_name = pd.projektordner_umbenennen(projekt_root, geruest)

    assert neuer_name == "Der-Markt-von-Rothenfeld"
    assert not projekt_root.exists()
    assert (tmp_path / "Der-Markt-von-Rothenfeld" / "projekt").is_dir()


def test_projektordner_umbenennen_ohne_titel_bleibt_unveraendert(tmp_path):
    projekt_root = tmp_path / "Rohtitel"
    (projekt_root / "projekt").mkdir(parents=True)

    neuer_name = pd.projektordner_umbenennen(projekt_root, "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815")

    assert neuer_name is None
    assert projekt_root.exists()


def test_projektordner_umbenennen_ueberspringt_wenn_kapitel_existieren(tmp_path):
    projekt_root = tmp_path / "Rohtitel"
    (projekt_root / "projekt").mkdir(parents=True)
    (projekt_root / "projekt" / "kapitel_01.md").write_text("Text", encoding="utf-8")
    geruest = "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n"

    neuer_name = pd.projektordner_umbenennen(projekt_root, geruest)

    assert neuer_name is None
    assert projekt_root.exists()


def test_projektordner_umbenennen_haengt_zaehler_an_wenn_zielname_existiert(tmp_path):
    projekt_root = tmp_path / "Rohtitel"
    (projekt_root / "projekt").mkdir(parents=True)
    (tmp_path / "Der-Markt-von-Rothenfeld").mkdir()
    geruest = "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n"

    neuer_name = pd.projektordner_umbenennen(projekt_root, geruest)

    assert neuer_name == "Der-Markt-von-Rothenfeld-2"
    assert not projekt_root.exists()
    assert (tmp_path / "Der-Markt-von-Rothenfeld-2" / "projekt").is_dir()


def test_projektordner_umbenennen_wiederholt_bei_transientem_permissionerror(tmp_path, monkeypatch):
    """Regression: Dropbox/Virenscanner/Suchindex halten geruest.md direkt
    nach dem Schreiben manchmal kurz offen - Windows verweigert dann das
    Umbenennen des Elternordners mit PermissionError(13), obwohl der
    Zustand Millisekunden spaeter schon wieder frei ist. Reproduziert live
    beobachtet: 'neuer_ordner' kam als null zurueck, obwohl Titel und
    Ordnerlogik korrekt waren."""
    projekt_root = tmp_path / "Rohtitel"
    (projekt_root / "projekt").mkdir(parents=True)
    geruest = "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n"

    monkeypatch.setattr(pd.time, "sleep", lambda _: None)  # Test nicht wirklich verzoegern

    echter_rename = Path.rename
    versuche = {"n": 0}

    def rename_mit_transientem_fehler(self, ziel):
        versuche["n"] += 1
        if versuche["n"] < 3:
            raise PermissionError(13, "Zugriff verweigert")
        return echter_rename(self, ziel)

    monkeypatch.setattr(Path, "rename", rename_mit_transientem_fehler)

    neuer_name = pd.projektordner_umbenennen(projekt_root, geruest)

    assert neuer_name == "Der-Markt-von-Rothenfeld"
    assert versuche["n"] == 3


def test_projektordner_umbenennen_gibt_nach_wiederholtem_fehler_auf(tmp_path, monkeypatch):
    projekt_root = tmp_path / "Rohtitel"
    (projekt_root / "projekt").mkdir(parents=True)
    geruest = "# STORY-GERUEST\n\n## Titel\nDer Markt von Rothenfeld\n"

    monkeypatch.setattr(pd.time, "sleep", lambda _: None)

    def rename_immer_fehler(self, ziel):
        raise PermissionError(13, "Zugriff verweigert")

    monkeypatch.setattr(Path, "rename", rename_immer_fehler)

    neuer_name = pd.projektordner_umbenennen(projekt_root, geruest)

    assert neuer_name is None
    assert projekt_root.exists()


def _quellprojekt_mit_schreibartefakten(tmp_path: Path) -> Path:
    """Baut ein Projekt, das so aussieht, als waere es fertig geschrieben -
    Grundlage fuer die projekt_fuer_neuschreiben_duplizieren()-Tests unten."""
    quelle = tmp_path / "Der-Markt-von-Rothenfeld"
    projekt = quelle / "projekt"
    projekt.mkdir(parents=True)
    (quelle / "personas").mkdir()
    (quelle / "personas" / "architekt.txt").write_text("Persona-Text", encoding="utf-8")
    (quelle / ".epoche").write_text("Mittelalter", encoding="utf-8")
    geruest = (
        "# STORY-GERUEST\n\n## Rahmen\nJahr: 1815\nAutor-Modell: Qwen3\n\n"
        "## Titel\nDer Markt von Rothenfeld\n\n## Kapitelplan\n"
        "Kapitel 1: Ankunft. Zielwortzahl: 1.000 Woerter.\n"
        "Kapitel 2: Aufloesung. Zielwortzahl: 1.000 Woerter.\n"
    )
    (projekt / "geruest.md").write_text(geruest, encoding="utf-8")
    (projekt / "verbotsliste.md").write_text("keine", encoding="utf-8")
    (projekt / "stand_00.md").write_text("Ausgangslage", encoding="utf-8")
    (projekt / "kapitel_01.md").write_text("Kapiteltext 1", encoding="utf-8")
    (projekt / "kapitel_02.md").write_text("Kapiteltext 2", encoding="utf-8")
    (projekt / "stand_01.md").write_text("Stand nach Kapitel 1", encoding="utf-8")
    (projekt / "befunde_01.json").write_text("{}", encoding="utf-8")
    (projekt / "automatik_status.json").write_text("{}", encoding="utf-8")
    (projekt / "automatik_verlauf.json").write_text("[]", encoding="utf-8")
    (projekt / "architekt_verlauf.json").write_text("{}", encoding="utf-8")
    (projekt / "geruest.md.1234567890.bak").write_text("alte Fassung", encoding="utf-8")
    (quelle / f"{quelle.name}.md").write_text("Kapiteltext 1\n\nKapiteltext 2", encoding="utf-8")
    return quelle


def test_projekt_fuer_neuschreiben_duplizieren_erzeugt_v2_ordner(tmp_path):
    quelle = _quellprojekt_mit_schreibartefakten(tmp_path)

    ziel = pd.projekt_fuer_neuschreiben_duplizieren(quelle)

    assert ziel == tmp_path / "Der-Markt-von-Rothenfeld_v2"
    assert ziel.is_dir()
    assert quelle.is_dir()  # Original bleibt unangetastet


def test_projekt_fuer_neuschreiben_duplizieren_haengt_hochzaehlend_v3_an_bei_kollision(tmp_path):
    quelle = _quellprojekt_mit_schreibartefakten(tmp_path)
    (tmp_path / "Der-Markt-von-Rothenfeld_v2").mkdir()

    ziel = pd.projekt_fuer_neuschreiben_duplizieren(quelle)

    assert ziel == tmp_path / "Der-Markt-von-Rothenfeld_v3"


def test_projekt_fuer_neuschreiben_duplizieren_loescht_schreib_artefakte(tmp_path):
    quelle = _quellprojekt_mit_schreibartefakten(tmp_path)

    ziel = pd.projekt_fuer_neuschreiben_duplizieren(quelle)
    projekt = ziel / "projekt"

    assert not (projekt / "kapitel_01.md").exists()
    assert not (projekt / "kapitel_02.md").exists()
    assert not (projekt / "stand_01.md").exists()
    assert not (projekt / "befunde_01.json").exists()
    assert not (projekt / "automatik_status.json").exists()
    assert not (projekt / "automatik_verlauf.json").exists()
    assert not (projekt / "architekt_verlauf.json").exists()
    assert not (projekt / "geruest.md.1234567890.bak").exists()
    assert not (ziel / f"{quelle.name}.md").exists()


def test_projekt_fuer_neuschreiben_duplizieren_behaelt_architekt_output(tmp_path):
    quelle = _quellprojekt_mit_schreibartefakten(tmp_path)

    ziel = pd.projekt_fuer_neuschreiben_duplizieren(quelle)
    projekt = ziel / "projekt"

    assert (projekt / "geruest.md").exists()
    assert (projekt / "verbotsliste.md").exists()
    assert (projekt / "stand_00.md").exists()
    assert (ziel / "personas" / "architekt.txt").exists()
    assert (ziel / ".epoche").read_text(encoding="utf-8") == "Mittelalter"


def test_projekt_fuer_neuschreiben_duplizieren_erzwingt_mistral(tmp_path):
    quelle = _quellprojekt_mit_schreibartefakten(tmp_path)

    ziel = pd.projekt_fuer_neuschreiben_duplizieren(quelle)
    geruest_text = (ziel / "projekt" / "geruest.md").read_text(encoding="utf-8")

    assert g.autor_rolle_erkennen(geruest_text) == "autor_mistral"
    assert "Qwen3" not in geruest_text
