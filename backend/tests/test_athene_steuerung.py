"""Client für den athene-steuerung-Dienst (Feature "KI- und Speicherkontrolle")."""
import httpx
import pytest

from app.core import athene_steuerung as ath


def test_meminfo_mb_rechnet_kb_in_mb():
    text = "MemTotal: 32000000 kB\nMemAvailable: 8000000 kB\nSwapTotal: 8000000 kB\nSwapFree: 2000000 kB\n"
    d = ath._meminfo_mb(text)
    assert d["ram"]["total_mb"] == 31250
    assert d["ram"]["used_mb"] == 31250 - 7812
    assert d["swap"]["used_mb"] == 7812 - 1953


def test_ollama_ps_parsen_liest_name_und_prozessor():
    text = (
        "NAME             ID              SIZE      PROCESSOR    CONTEXT    UNTIL\n"
        "gemma4:latest    c6eb396dbd59    3.3 GB    100% GPU     16384      22 minutes from now\n"
    )
    modelle = ath._ollama_ps_parsen(text)
    assert modelle == [{"name": "gemma4:latest", "processor": "100% GPU"}]


def test_status_aus_dienst_dampft_auf_konfigurierte_container_ein():
    roh = {
        "ram": {"total_mb": 30000, "available_mb": 20000, "used_mb": 10000},
        "swap": {"total_mb": 8000, "used_mb": 1000},
        "containers": [
            {"name": "sd-server", "running": False},
            {"name": "sd-server-pony", "running": True},
            {"name": "irgendwas-anderes", "running": True},
        ],
        "ollama": [{"name": "gemma4:latest", "processor": "100% GPU"}],
    }
    d = ath._status_aus_dienst(roh, ["sd-server", "sd-server-pony"])
    assert d["verfuegbar"] is True
    assert d["containers"] == [
        {"name": "sd-server", "running": False},
        {"name": "sd-server-pony", "running": True},
    ]


def test_herunterfahren_empfohlen_nur_bei_laufendem_container_und_speicherdruck():
    laeuft = [{"name": "sd-server", "running": True}]
    aus = [{"name": "sd-server", "running": False}]

    # läuft + Swap in Benutzung -> ja
    assert ath.herunterfahren_empfohlen(
        {"containers": laeuft, "swap": {"used_mb": 3000}, "ram": {"available_mb": 20000}}
    ) is True
    # läuft + wenig RAM frei -> ja
    assert ath.herunterfahren_empfohlen(
        {"containers": laeuft, "swap": {"used_mb": 0}, "ram": {"available_mb": 3000}}
    ) is True
    # läuft, aber genug Speicher -> nein
    assert ath.herunterfahren_empfohlen(
        {"containers": laeuft, "swap": {"used_mb": 0}, "ram": {"available_mb": 20000}}
    ) is False
    # Speicherdruck, aber nichts läuft -> nein
    assert ath.herunterfahren_empfohlen(
        {"containers": aus, "swap": {"used_mb": 5000}, "ram": {"available_mb": 1000}}
    ) is False


def test_status_ueber_http_setzt_bearer_und_normalisiert(monkeypatch):
    aufgerufen = {}

    def fake_get(self, url, headers=None):
        aufgerufen["url"] = url
        aufgerufen["auth"] = headers["Authorization"]
        return httpx.Response(200, json={
            "ram": {"total_mb": 30000, "available_mb": 19000, "used_mb": 11000},
            "swap": {"total_mb": 8000, "used_mb": 1400},
            "containers": [{"name": "sd-server", "running": False},
                           {"name": "sd-server-pony", "running": True}],
            "ollama": [],
        })

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    d = ath.status_ueber_http("http://127.0.0.1:18324", "geheim123", ["sd-server", "sd-server-pony"])
    assert aufgerufen["url"] == "http://127.0.0.1:18324/status"
    assert aufgerufen["auth"] == "Bearer geheim123"
    assert d["verfuegbar"] is True
    assert d["ram"]["used_mb"] == 11000


def test_status_ueber_http_wirft_steuerfehler_bei_verbindungsproblem(monkeypatch):
    def fake_get(self, url, headers=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    with pytest.raises(ath.SteuerFehler):
        ath.status_ueber_http("http://127.0.0.1:18324", "t", ["sd-server"])


def test_container_ueber_http_meldet_fehlertext_aus_json(monkeypatch):
    def fake_post(self, url, headers=None):
        return httpx.Response(403, json={"fehler": "Container 'x' ist nicht steuerbar"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    with pytest.raises(ath.SteuerFehler, match="nicht steuerbar"):
        ath.container_ueber_http("http://127.0.0.1:18324", "t", "x", "stop")
