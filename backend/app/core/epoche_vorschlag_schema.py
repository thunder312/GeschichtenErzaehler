"""Pydantic-Modell fuer die strukturierte Antwort der Rolle 'analysator'
bei AUFGABE: EPOCHE-VORSCHLAG (siehe app/data/personas/analysator.txt) -
analog zu app/core/fundus_schema.py, aber fuer die Ableitung eines
Epoche-Formulars (dieselben Felder wie EpocheErstellenAnfrage/
app/core/epoche.py:EpocheAntworten) aus einem importierten Fremdtext."""
from __future__ import annotations

from pydantic import BaseModel


class EpocheVorschlagAntwortLLM(BaseModel):
    name: str = ""
    erfunden: bool = False
    beschreibung: str = ""
    zeitraum: str = ""
    orte: str = ""
    gesellschaft: str = ""
    statusregel: str = ""
    genre: str = ""
    rang_wort: str = ""
    anreden: str = ""
    nebenstrang_typen: str = ""
    vorbild_franchise: str = ""
    verbote_start: str = ""
