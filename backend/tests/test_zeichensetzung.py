"""Deterministische Zeichensetzungs-Pruefung (kein KI-Aufruf): fehlendes
Leerzeichen nach Satzzeichen und unpaarige Anfuehrungszeichen - typische
Folgen einer verrutschten Pruefer-Ersetzung, die der LLM-Lektor regelmaessig
uebersieht (Vorfall "Die-Bibliothek-der-verborgenen-Kapitel", Kapitel 2)."""
from app.api.pipeline import _zeichensetzung_roh_befunde
from app.core import heuristik as h


def test_fehlendes_leerzeichen_nach_punkt_wird_erkannt():
    text = "Sie tastete sich vorwärts.Die Bibliothek lag hinter ihr."
    findings = h.zeichensetzung_pruefen(text)
    codes = [f.code for f in findings]
    assert "fehlendes_leerzeichen" in codes
    assert "vorwärts.Die" in next(f.meldung for f in findings if f.code == "fehlendes_leerzeichen")


def test_gaengige_abkuerzungen_loesen_keinen_fehlalarm_aus():
    text = "Das war z.B. gefährlich, u.a. wegen d.h. der Kälte. Alles ruhig."
    assert h.zeichensetzung_pruefen(text) == []


def test_dreipunkt_auslassung_ist_kein_fehlendes_leerzeichen():
    text = "Ich weiß nicht...Der Gedanke war zu schwer. Sie schwieg."
    assert [f for f in h.zeichensetzung_pruefen(text) if f.code == "fehlendes_leerzeichen"] == []


def test_unpaarige_typografische_anfuehrungszeichen_werden_erkannt():
    text = "Er sagte: „Ich lasse mich nicht abschrecken.Ihre Worte klangen fest."
    codes = [f.code for f in h.zeichensetzung_pruefen(text)]
    assert "anfuehrungszeichen_unpaarig" in codes


def test_sauberer_dialog_ist_unauffaellig():
    text = "„Du bist pünktlich.“ Sie nickte. „Natürlich bin ich das.“"
    assert h.zeichensetzung_pruefen(text) == []


def test_zeichensetzung_haengt_an_alle_nachbearbeitungs_checks():
    text = "Er ging weg.Sie blieb zurück."
    findings = h.alle_nachbearbeitungs_checks(text, geruest="", stufe="mild")
    assert any(f.code == "fehlendes_leerzeichen" for f in findings)


def test_roh_befund_liefert_ein_klick_vorschlag_mit_leerzeichen():
    kapiteltext = "Staubige Regale säumten die Wände und warfen Schatten an die Decke.Auf dem Tisch lag ein Buch."
    befunde = _zeichensetzung_roh_befunde(kapiteltext)

    assert len(befunde) == 1
    b = befunde[0]
    assert b.kategorie == "lektorat"
    assert b.fundstelle == "Decke.Auf"
    assert b.vorschlag == "Decke. Auf"
    assert kapiteltext[b.start:b.end] == "Decke.Auf"


def test_roh_befund_dedupliziert_gleiche_stelle():
    kapiteltext = "Ende.Anfang und nochmal Ende.Anfang."
    befunde = _zeichensetzung_roh_befunde(kapiteltext)
    assert [b.fundstelle for b in befunde] == ["Ende.Anfang"]


def test_roh_befund_leer_bei_sauberem_text():
    assert _zeichensetzung_roh_befunde("Ein ganz normaler Satz. Und noch einer.") == []
