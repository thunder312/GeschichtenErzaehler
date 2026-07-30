"""Pydantic-Modell fuer die strukturierte Antwort der Rolle 'fundus_pfleger'
(siehe app/core/rollen.py) - analog zu app/core/pruef_schema.py, aber fuer
die Figuren-Extraktion aus dem '## Figuren'-Abschnitt eines Geruests
(app/core/fundus.py:figuren_zusammenfuehren)."""
from __future__ import annotations

from pydantic import BaseModel


class FundusFigurEintrag(BaseModel):
    name: str
    alter: str = ""
    stand: str = ""
    eigenschaften: str = ""


class FundusExtraktionAntwortLLM(BaseModel):
    figuren: list[FundusFigurEintrag] = []
