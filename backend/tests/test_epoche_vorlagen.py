from app.core.epoche import EpocheAntworten, einleitungssatz_vorlage


def _antworten(**overrides) -> EpocheAntworten:
    daten = {
        "name": "Neo-Berlin",
        "erfunden": True,
        "beschreibung": "einer erfundenen Cyberpunk-Welt",
        "zeitraum": "Jahr 2088",
        "orte": "Neo-Berlin, Unterstadt",
        "gesellschaft": "Konzerne herrschen.",
        "statusregel": "Wer keinen Konzern-Ausweis hat, zählt nicht.",
        "vorbild_franchise": "",
    }
    daten.update(overrides)
    return EpocheAntworten(**daten)


def test_einleitungssatz_ohne_franchise_bleibt_schlicht():
    satz = einleitungssatz_vorlage(_antworten())
    assert satz == "Eine Geschichte aus dem Neo-Berlin im Jahre {jahr}"


def test_einleitungssatz_bei_realer_epoche_ignoriert_vorbild_franchise():
    """vorbild_franchise wird nur bei erfunden=True beruecksichtigt - eine
    reale Epoche braucht keinen FanFic-Hinweis."""
    satz = einleitungssatz_vorlage(_antworten(erfunden=False, vorbild_franchise="Irgendwas"))
    assert "FanFic" not in satz
    assert satz == "Eine Geschichte aus dem Neo-Berlin im Jahre {jahr}"


def test_einleitungssatz_mit_franchise_enthaelt_fanfic_hinweis():
    satz = einleitungssatz_vorlage(_antworten(vorbild_franchise="Cyberpunk 2077"))
    assert satz.startswith("Eine Geschichte aus dem Neo-Berlin im Jahre {jahr}")
    assert "Cyberpunk 2077" in satz
    assert "FanFic" in satz
    assert "ohne jegliche Rechte" in satz
    assert "kommerziell" in satz.lower()
    # Bewusst EIN durchgehender Satz ohne Leerzeile - titelseite_erzeugen()
    # umschliesst den kompletten Einleitungssatz mit einem einzelnen "*...*"
    # Markdown-Kursivpaar, das ueber eine Leerzeile hinweg nicht mehr als
    # Kursivtext erkannt wuerde.
    assert "\n\n" not in satz
    assert "{jahr}" in satz


def test_einleitungssatz_platzhalter_bleibt_ersetzbar():
    from app.core.geruest import titelseite_erzeugen

    satz = einleitungssatz_vorlage(_antworten(vorbild_franchise="Cyberpunk 2077"))
    geruest = "# STORY-GERUEST\n\n## Rahmen\nJahr: 2088\n\n## Titel\nNeon-Schatten\n"
    titelseite = titelseite_erzeugen(geruest, "Neo-Berlin", satz)
    assert "2088" in titelseite
    assert "{jahr}" not in titelseite
    assert "Cyberpunk 2077" in titelseite
