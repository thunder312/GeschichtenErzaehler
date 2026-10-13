"""Tests fuer app/core/herunterfahren.py - ohne echten shutdown-Aufruf."""
import subprocess

import pytest

from app.core import herunterfahren as hf


def test_unter_linux_nicht_moeglich_und_planen_wirft(monkeypatch):
    monkeypatch.setattr(hf.sys, "platform", "linux")
    assert hf.moeglich() is False
    with pytest.raises(hf.HerunterfahrenFehler):
        hf.planen()


def test_planen_ruft_shutdown_mit_vorlauf_auf(monkeypatch):
    monkeypatch.setattr(hf.sys, "platform", "win32")
    aufrufe = []

    def _run(cmd, **kwargs):
        aufrufe.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(hf.subprocess, "run", _run)
    hf.planen(45)
    hf.abbrechen()
    assert aufrufe[0][:4] == ["shutdown", "/s", "/t", "45"]
    assert aufrufe[1] == ["shutdown", "/a"]


def test_abbrechen_ohne_geplantes_herunterfahren_wirft(monkeypatch):
    monkeypatch.setattr(hf.sys, "platform", "win32")
    monkeypatch.setattr(
        hf.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1116, "", "Keine Abmeldung läuft."),
    )
    with pytest.raises(hf.HerunterfahrenFehler):
        hf.abbrechen()
