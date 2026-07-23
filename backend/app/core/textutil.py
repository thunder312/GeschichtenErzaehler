"""Kleine Text-Hilfsfunktionen, 1:1 aus novelle.py uebernommen."""
import re


def woerter(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))
