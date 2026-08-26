from app.core import befunde_ablehnung
from app.core.befunde_merge import RoherBefund


def _roh(kategorie="anachronismus", fundstelle="Ein laengerer Zitatausschnitt", vorschlag="x"):
    return RoherBefund(
        kategorie=kategorie, fundstelle=fundstelle, beschreibung="Problem",
        sicherheit="hoch", vorschlag=vorschlag, start=0, end=len(fundstelle),
    )


def test_hinzufuegen_und_herausfiltern_entfernt_exakten_treffer(tmp_path):
    roh = [_roh()]
    befunde_ablehnung.hinzufuegen(tmp_path, ["anachronismus"], roh[0].fundstelle)

    ergebnis = befunde_ablehnung.herausfiltern(tmp_path, roh)

    assert ergebnis == []


def test_herausfiltern_laesst_andere_kategorie_unberuehrt(tmp_path):
    roh = [_roh(kategorie="anachronismus")]
    befunde_ablehnung.hinzufuegen(tmp_path, ["kontinuitaet"], roh[0].fundstelle)

    ergebnis = befunde_ablehnung.herausfiltern(tmp_path, roh)

    assert ergebnis == roh


def test_herausfiltern_laesst_andere_fundstelle_unberuehrt(tmp_path):
    roh = [_roh(fundstelle="Ein voellig anderer Ausschnitt")]
    befunde_ablehnung.hinzufuegen(tmp_path, ["anachronismus"], "Ein laengerer Zitatausschnitt")

    ergebnis = befunde_ablehnung.herausfiltern(tmp_path, roh)

    assert ergebnis == roh


def test_ist_abgelehnt_erkennt_auch_teilweise_ueberlappende_fundstelle(tmp_path):
    # Ein gemergter Fund (siehe befunde_merge.py) kann eine breitere Spanne
    # abdecken als das Zitat, das eine einzelne Pruefer-Rolle beim naechsten
    # Lauf allein (ohne Cluster-Partner) meldet - Enthaltensein in beide
    # Richtungen soll trotzdem als abgelehnt erkannt werden.
    befunde_ablehnung.hinzufuegen(tmp_path, ["anachronismus"], "Der Zauberer reiste nach London und blieb dort")

    abgelehnte = befunde_ablehnung.lesen(tmp_path)

    # Schmaleres Zitat, das vollstaendig in der zuvor abgelehnten (breiteren)
    # Fundstelle steckt.
    assert befunde_ablehnung.ist_abgelehnt(abgelehnte, "anachronismus", "reiste nach London")
    assert befunde_ablehnung.ist_abgelehnt(abgelehnte, "anachronismus", "Der Zauberer reiste nach London und blieb dort")
    assert not befunde_ablehnung.ist_abgelehnt(abgelehnte, "kontinuitaet", "reiste nach London")


def test_kurze_fundstellen_werden_nie_ueber_enthaltensein_abgeglichen(tmp_path):
    # Schutz gegen falsch-positive Treffer durch ein einzelnes gemeinsames
    # Wort (siehe _MINDESTLAENGE_ENTHALTEN).
    befunde_ablehnung.hinzufuegen(tmp_path, ["lektorat"], "und")

    abgelehnte = befunde_ablehnung.lesen(tmp_path)

    assert not befunde_ablehnung.ist_abgelehnt(abgelehnte, "lektorat", "und dann ging er los")


def test_hinzufuegen_ist_idempotent(tmp_path):
    befunde_ablehnung.hinzufuegen(tmp_path, ["anachronismus"], "Ein laengerer Zitatausschnitt")
    befunde_ablehnung.hinzufuegen(tmp_path, ["anachronismus"], "Ein laengerer Zitatausschnitt")

    assert len(befunde_ablehnung.lesen(tmp_path)) == 1
