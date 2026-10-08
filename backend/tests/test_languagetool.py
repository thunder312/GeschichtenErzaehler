import asyncio

import httpx

from app.core import languagetool as lt


def _mit_antwort(monkeypatch, matches, status=200):
    class _Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, data=None):
            assert url == "http://lt/v2/check"
            return httpx.Response(status, json={"matches": matches}, request=httpx.Request("POST", url))
    monkeypatch.setattr(lt.httpx, "AsyncClient", _Client)


def _match(rule, offset, length, werte):
    return {"rule": {"id": rule}, "offset": offset, "length": length,
            "replacements": [{"value": w} for w in werte]}


def test_ohne_url_keine_funde():
    assert asyncio.run(lt.grammatik_befunde("Text", "")) == []


def test_eindeutiger_vorschlag_wird_uebernehmbar(monkeypatch):
    text = "Er trank einen kühlen Gemisch."
    _mit_antwort(monkeypatch, [_match("DE_AGREEMENT", 9, 20, ["einem kühlen Gemisch"])])
    (b,) = asyncio.run(lt.grammatik_befunde(text, "http://lt/"))
    assert (b.fundstelle, b.vorschlag, b.kategorie) == ("einen kühlen Gemisch", "einem kühlen Gemisch", "lektorat")
    assert text[b.start:b.end] == b.fundstelle


def test_mehrere_varianten_ohne_vorschlag(monkeypatch):
    _mit_antwort(monkeypatch, [_match("DE_AGREEMENT", 7, 8, ["die Frau", "der Frau"])])
    (b,) = asyncio.run(lt.grammatik_befunde("Er sah das Frau.", "http://lt"))
    assert b.vorschlag is None
    assert "die Frau / der Frau" in b.beschreibung


def test_unbekannte_regeln_werden_ignoriert(monkeypatch):
    _mit_antwort(monkeypatch, [_match("GERMAN_SPELLER_RULE", 0, 9, ["Kommandeur"])])
    assert asyncio.run(lt.grammatik_befunde("Commander", "http://lt")) == []


def test_serverfehler_liefert_leere_liste(monkeypatch):
    _mit_antwort(monkeypatch, [], status=500)
    assert asyncio.run(lt.grammatik_befunde("Text", "http://lt")) == []
