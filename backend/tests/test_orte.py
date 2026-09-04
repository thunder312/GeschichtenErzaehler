from app.core import orte as ort_modul


def test_leere_vorlage_enthaelt_kommentarblock():
    vorlage = ort_modul.leere_vorlage()
    assert vorlage.startswith("<!--")
    assert "ORTE-VORLAGE" in vorlage


def test_kopf_kommentar_extrahieren_ohne_epoche_liefert_vorlage():
    assert ort_modul.kopf_kommentar_extrahieren("") == ort_modul.leere_vorlage()


def test_kopf_kommentar_extrahieren_findet_text_vor_erster_epoche():
    text = "<!-- eigener Kopf -->\n\n## Regency\n\n### Marktplatz\n- Beschreibung: Belebt.\n"
    assert ort_modul.kopf_kommentar_extrahieren(text) == "<!-- eigener Kopf -->\n\n"


def test_ort_block_erzeugen():
    block = ort_modul.ort_block_erzeugen(
        ort_modul.Ort(epoche="Regency", name="Marktplatz von Rothenfeld",
                      beschreibung="Belebter Platz\nim Herzen der Stadt")
    )
    assert block == "### Marktplatz von Rothenfeld\n- Beschreibung: Belebter Platz im Herzen der Stadt\n"


def test_orte_parsen_liest_mehrere_epochen():
    text = (
        ort_modul.leere_vorlage()
        + "\n## Regency\n\n### Marktplatz\n- Beschreibung: Belebter Platz.\n"
        + "\n### Anwesen Rothenfeld\n- Beschreibung: Herrschaftliches Landhaus.\n"
        + "\n## Mittelalter\n\n### Burgverlies\n- Beschreibung: Kalt und feucht.\n"
    )
    orte = ort_modul.orte_parsen(text)
    assert [(o.epoche, o.name, o.beschreibung) for o in orte] == [
        ("Regency", "Marktplatz", "Belebter Platz."),
        ("Regency", "Anwesen Rothenfeld", "Herrschaftliches Landhaus."),
        ("Mittelalter", "Burgverlies", "Kalt und feucht."),
    ]


def test_orte_parsen_ohne_epoche_liefert_leere_liste():
    assert ort_modul.orte_parsen(ort_modul.leere_vorlage()) == []


def test_orte_serialisieren_parsen_roundtrip():
    # Bereits nach Epoche gruppiert (erste Auftrittsreihenfolge) - orte_serialisieren()
    # gruppiert nach Epoche, das Parsen liefert danach dieselbe Reihenfolge zurueck.
    orte = [
        ort_modul.Ort(epoche="Regency", name="Marktplatz", beschreibung="Belebter Platz."),
        ort_modul.Ort(epoche="Regency", name="Anwesen Rothenfeld", beschreibung="Herrschaftliches Landhaus."),
        ort_modul.Ort(epoche="Mittelalter", name="Burgverlies", beschreibung="Kalt und feucht."),
    ]
    text = ort_modul.orte_serialisieren(orte)
    assert ort_modul.orte_parsen(text) == orte
