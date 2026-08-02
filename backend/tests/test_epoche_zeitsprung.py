from app.core.epoche import zeitsprung_dateien_zusammenfuehren


def _dateien(**overrides):
    basis = {
        "architekt.txt": "Du bist Erzaehlarchitekt fuer Epoche A.",
        "autor.txt": "Du bist Autor fuer Epoche A.",
        "pruefer_anachronismus.txt": "Du bist Pruefer fuer Epoche A.",
        "verbotsliste.md": "# Verbotsliste A\n- Eisenbahn",
    }
    basis.update(overrides)
    return basis


def test_zeitsprung_zusammenfuehren_haengt_referenzblock_an_alle_dateien():
    primaer = _dateien()
    sekundaer = {
        "architekt.txt": "Du bist Erzaehlarchitekt fuer Epoche B.",
        "autor.txt": "Du bist Autor fuer Epoche B.",
        "pruefer_anachronismus.txt": "Du bist Pruefer fuer Epoche B.",
        "verbotsliste.md": "# Verbotsliste B\n- Laserschwerter",
    }

    ergebnis = zeitsprung_dateien_zusammenfuehren("Epoche A", primaer, "Epoche B", sekundaer)

    assert "Du bist Erzaehlarchitekt fuer Epoche A." in ergebnis["architekt.txt"]
    assert "ZEITSPRUNG" in ergebnis["architekt.txt"]
    assert "Du bist Erzaehlarchitekt fuer Epoche B." in ergebnis["architekt.txt"]

    assert "ZEITSPRUNG" in ergebnis["autor.txt"]
    assert "Du bist Autor fuer Epoche B." in ergebnis["autor.txt"]

    assert "ZEITSPRUNG" in ergebnis["pruefer_anachronismus.txt"]
    assert "Du bist Pruefer fuer Epoche B." in ergebnis["pruefer_anachronismus.txt"]

    verbotsliste = ergebnis["verbotsliste.md"]
    assert "## Epoche: Epoche A" in verbotsliste
    assert "- Eisenbahn" in verbotsliste
    assert "## Epoche: Epoche B" in verbotsliste
    assert "- Laserschwerter" in verbotsliste


def test_zeitsprung_zusammenfuehren_laesst_datei_unveraendert_wenn_sekundaer_sie_nicht_hat():
    primaer = _dateien()
    sekundaer = {"autor.txt": "Du bist Autor fuer Epoche B."}

    ergebnis = zeitsprung_dateien_zusammenfuehren("Epoche A", primaer, "Epoche B", sekundaer)

    assert ergebnis["architekt.txt"] == primaer["architekt.txt"]
    assert ergebnis["pruefer_anachronismus.txt"] == primaer["pruefer_anachronismus.txt"]
    assert ergebnis["verbotsliste.md"] == primaer["verbotsliste.md"]
    assert "ZEITSPRUNG" in ergebnis["autor.txt"]
