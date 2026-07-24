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
