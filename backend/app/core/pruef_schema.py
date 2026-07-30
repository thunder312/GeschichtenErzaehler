"""Pydantic-Modelle fuer die STRUKTURIERTEN Antworten der beiden parallel
laufenden Pruefer-Rollen ("anachronismus", "kontinuitaet") - ersetzt das
frueher freiformulierte Markdown (Tabelle bzw. nummerierte Liste), damit
Fundstellen zuverlaessig im Kapiteltext wiedergefunden (siehe fundstellen.py)
und ueberlappende Funde beider Pruefer deterministisch zusammengefuehrt
werden koennen (siehe befunde_merge.py), ohne bruechiges Markdown-Parsing.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AnachronismusEintrag(BaseModel):
    kategorie: Literal["anachronismus", "stimmigkeit"]
    fundstelle: str
    problem: str
    sicherheit: Literal["hoch", "mittel", "gering"]
    vorschlag: str | None = None


class AnachronismusAntwortLLM(BaseModel):
    befunde: list[AnachronismusEintrag] = []


class KontinuitaetEintrag(BaseModel):
    zitat: str
    widerspruch: str
    beleg: str
    unsicher: bool = False
    vorschlag: str | None = None


class KontinuitaetAntwortLLM(BaseModel):
    befunde: list[KontinuitaetEintrag] = []


class LektorEintrag(BaseModel):
    fundstelle: str
    problem: str
    vorschlag: str


class LektorAntwortLLM(BaseModel):
    befunde: list[LektorEintrag] = []
