import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "kapitelueberschrift_bereinigen",
    Path(__file__).resolve().parent.parent / "scripts" / "kapitelueberschrift_bereinigen.py",
)
kb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kb)


PROSA = (
    "Die Sonne stand hoch über dem Anwesen von Torii Yorinaga, als Genzō das "
    "junge Mädchen unsanft vor sich her stieß.\n\nFuki stolperte auf den Hof."
)


def test_doppelte_ueberschrift_mit_titelseite_wird_zusammengefasst():
    text = (
        "# Das Recht des Samurais\n\n"
        "*Eine Geschichte aus dem japanischen Hochmittelalter im Jahre 1250*\n\n\n"
        "Kapitel eins: Rechtlose Magd\n\n"
        "### Kapitel eins: Rechtlose Magd\n\n"
        f"{PROSA}\n"
    )
    neu, beschreibung = kb.bereinige(text)
    assert neu == (
        "# Das Recht des Samurais\n\n"
        "*Eine Geschichte aus dem japanischen Hochmittelalter im Jahre 1250*\n\n"
        "Kapitel eins: Rechtlose Magd\n\n"
        f"{PROSA}\n"
    )
    assert "Rechtlose Magd" in beschreibung
    assert neu.count("Kapitel eins: Rechtlose Magd") == 1
    assert "### " not in neu


def test_doppelte_ueberschrift_ohne_titelseite():
    text = f"Kapitel drei: Der nächste Tag\n\n### Kapitel drei: Der nächste Tag\n\n{PROSA}\n"
    neu, _ = kb.bereinige(text)
    assert neu == f"Kapitel drei: Der nächste Tag\n\n{PROSA}\n"


def test_nur_markdown_ueberschrift_wird_klartext():
    text = f"### Kapitel vier: Die letzte Grenze\n\n{PROSA}\n"
    neu, beschreibung = kb.bereinige(text)
    assert neu == f"Kapitel vier: Die letzte Grenze\n\n{PROSA}\n"
    assert "Klartext" in beschreibung


def test_einzelne_klartext_ueberschrift_bleibt():
    text = f"Kapitel zwei: Die Wendung\n\n{PROSA}\n"
    assert kb.bereinige(text) is None


def test_einzelne_fett_ueberschrift_bleibt():
    text = f"**Kapitel eins: Der Anfang**\n\n{PROSA}\n"
    assert kb.bereinige(text) is None


def test_prosa_mit_kapitel_erwaehnung_bleibt_unangetastet():
    text = (
        "Kapitel eins: Der Anfang\n\n"
        "Sie dachte an das, was in Kapitel zwei: der Wendepunkt, geschehen würde.\n"
    )
    # Nur EINE echte Ueberschrift am Anfang, die Erwaehnung im Fliesstext
    # zaehlt nicht (steht nicht am Zeilenanfang direkt nach der Ueberschrift).
    assert kb.bereinige(text) is None


def test_trailing_newline_wird_beibehalten_oder_weggelassen():
    ohne = "Kapitel eins: X\n\n### Kapitel eins: X\n\nEin Satz."
    neu, _ = kb.bereinige(ohne)
    assert neu == "Kapitel eins: X\n\nEin Satz."
    assert not neu.endswith("\n")


def test_bereinige_ist_idempotent():
    text = f"Kapitel eins: Rechtlose Magd\n\n### Kapitel eins: Rechtlose Magd\n\n{PROSA}\n"
    neu, _ = kb.bereinige(text)
    assert kb.bereinige(neu) is None


def test_skript_end_to_end_mit_backup_und_export(tmp_path):
    story = tmp_path / "daniel" / "Japan" / "Das-Recht-des-Samurais"
    projekt = story / "projekt"
    projekt.mkdir(parents=True)
    (projekt / "kapitel_01.md").write_text(
        f"Kapitel eins: Rechtlose Magd\n\n### Kapitel eins: Rechtlose Magd\n\n{PROSA}\n",
        encoding="utf-8",
    )
    (projekt / "kapitel_02.md").write_text(f"Kapitel zwei: Sauber\n\n{PROSA}\n", encoding="utf-8")
    (story / "Das-Recht-des-Samurais.md").write_text("alt und veraltet", encoding="utf-8")

    import sys

    argv = sys.argv
    sys.argv = ["x", str(tmp_path), "--apply"]
    try:
        kb.main()
    finally:
        sys.argv = argv

    k1 = (projekt / "kapitel_01.md").read_text(encoding="utf-8")
    assert k1.count("Kapitel eins: Rechtlose Magd") == 1 and "### " not in k1
    assert PROSA in k1
    # unveraendertes Kapitel bleibt ohne .bak
    assert list(projekt.glob("kapitel_01.md.*.bak"))
    assert not list(projekt.glob("kapitel_02.md.*.bak"))
    # Export neu aufgebaut, alte Fassung gesichert
    export = (story / "Das-Recht-des-Samurais.md").read_text(encoding="utf-8")
    assert "### " not in export and PROSA in export
    assert list(story.glob("Das-Recht-des-Samurais.md.*.bak"))
