"""Satzbau-Pruefer (Verb-Letzt): Vorschlaege duerfen nur umstellen, nicht
Verbformen aendern (realer Fund: "als fuerchte sie" -> "als sie fuerchtete")."""
import json

from app.api.pipeline import _nur_umgestellt, _satzbau_roh_befunde


def test_reine_umstellung_ist_erlaubt():
    assert _nur_umgestellt("dass sie ist müde", "dass sie müde ist")
    assert _nur_umgestellt("wo ihr Griff zitterte leicht", "wo ihr Griff leicht zitterte")
    assert _nur_umgestellt("der Mann, der kam spät nach Hause", "der Mann, der spät nach Hause kam")


def test_verbklammer_zusammenziehen_ist_erlaubt():
    assert _nur_umgestellt(
        "bis das Licht drang durch das Fenster ein", "bis das Licht durch das Fenster eindrang"
    )


def test_gross_kleinschreibung_und_satzzeichen_egal():
    assert _nur_umgestellt("Weil er war müde.", "weil er müde war")


def test_geaenderte_verbform_ist_keine_umstellung():
    assert not _nur_umgestellt("als fürchte sie, etwas falsch zu machen.", "als sie fürchtete, etwas falsch zu machen.")
    assert not _nur_umgestellt("dass sie ist müde", "dass sie müde war")
    assert not _nur_umgestellt("weil er kam", "weil er kommt")


def _antwort(fundstelle, vorschlag):
    return json.dumps({"befunde": [{
        "fundstelle": fundstelle, "problem": "Verb-Letzt-Stellung verletzt", "vorschlag": vorschlag,
    }]})


TEXT = 'Sie lächelte, als fürchte sie, etwas falsch zu machen. Danach schwieg sie.'


def test_befund_bleibt_aber_ohne_vorschlag_bei_geaenderter_verbform():
    fund = "als fürchte sie, etwas falsch zu machen."
    ergebnis = _satzbau_roh_befunde(TEXT, _antwort(fund, "als sie fürchtete, etwas falsch zu machen."))
    assert len(ergebnis) == 1
    assert ergebnis[0].vorschlag is None
    assert ergebnis[0].fundstelle == fund
    assert ergebnis[0].start is not None  # Stelle weiterhin im Text markiert
    assert "kein Vorschlag" in ergebnis[0].beschreibung


def test_echte_umstellung_behaelt_den_vorschlag():
    text = "Er sagte, dass sie ist müde. Dann ging er."
    ergebnis = _satzbau_roh_befunde(text, _antwort("dass sie ist müde", "dass sie müde ist"))
    assert len(ergebnis) == 1
    assert ergebnis[0].vorschlag == "dass sie müde ist"
    assert "kein Vorschlag" not in ergebnis[0].beschreibung
