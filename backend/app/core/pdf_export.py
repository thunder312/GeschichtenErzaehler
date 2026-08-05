"""Erzeugt ein gestaltetes Buch-PDF aus den Kapiteldateien eines Projekts -
fuer den "PDF herunterladen"-Knopf im Stand & Export-Tab. Reine Formatierung
auf Basis der bereits vorhandenen Kapiteltexte, kein Ollama-Aufruf hier.
"""
from __future__ import annotations

import io
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, Image, PageBreak, PageTemplate, Paragraph, Spacer

from app.core.geruest import titel_erkennen, titelseite_erzeugen

ZIERZEICHEN = "❦"

_UNTERTITEL_ZEILE_RE = re.compile(r"^\*(.+?)\*\s*$", re.MULTILINE)

# Die Kapitelueberschrift-Zeile, die JEDE Kapiteldatei einleitet (Format
# laut Autor-Persona: "Kapitel eins: Sprechender Untertitel"). Das Modell
# setzt sie nicht zuverlaessig in Markdown-Fett ("**...**") - Kapitel 1
# tut es haeufig (weil die Titelseiten-Zeilen davor stehen), alle
# folgenden Kapitel oft nicht. Die Erkennung darf sich deshalb NICHT auf
# "**" verlassen, sondern muss beide Varianten abdecken, sonst wird die
# Ueberschrift als gewoehnlicher Absatz mitgerendert (linksbuendig, falsche
# Schrift, und der Kapitelname erscheint doppelt).
_KAPITEL_UEBERSCHRIFT_RE = re.compile(
    r"^\*{0,2}Kapitel\s+\S+\s*[:\-–—]\s*(.+?)\*{0,2}\s*$", re.IGNORECASE
)


def _kapitel_parsen(text: str) -> tuple[str | None, list[str]]:
    """Trennt eine Kapiteldatei in (Kapitel-Untertitel, Absaetze). Ueberspringt
    die Titelseiten-Zeilen ("# Titel", "*Untertitel*"), die nur in Kapitel 1
    vorkommen (siehe geruest.titelseite_erzeugen), und erkennt die
    "Kapitel N: ..."-Ueberschrift, die jede Kapiteldatei einleitet."""
    zeilen = text.strip().split("\n")
    rest_start = 0
    untertitel: str | None = None
    for i, zeile in enumerate(zeilen):
        z = zeile.strip()
        if not z:
            continue
        if z.startswith("# ") or (z.startswith("*") and z.endswith("*") and not z.startswith("**")):
            continue
        treffer = _KAPITEL_UEBERSCHRIFT_RE.match(z)
        if treffer:
            untertitel = treffer.group(1).strip()
            rest_start = i + 1
        else:
            rest_start = i
        break

    rest = "\n".join(zeilen[rest_start:]).strip()
    absaetze = [re.sub(r"[ \t]+", " ", p.strip()) for p in re.split(r"\n\s*\n", rest) if p.strip()]
    return untertitel, absaetze


def _roemisch(zahl: int) -> str:
    werte = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    ergebnis = ""
    for wert, symbol in werte:
        while zahl >= wert:
            ergebnis += symbol
            zahl -= wert
    return ergebnis or str(zahl)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _seitenzahl_zeichner(seiten_ohne_nummer: int):
    """Baut den onPage-Callback fuer die Seitenzahl. seiten_ohne_nummer ist
    1 (nur Titelseite) oder 2 (Cover + Titelseite, siehe cover_bytes-Parameter
    von buch_pdf_erzeugen) - die Zaehlung der sichtbaren Seitenzahlen (Kapitel
    1 = "1") bleibt so unabhaengig davon, ob ein Cover vorangestellt ist."""
    def zeichnen(canvas: Canvas, dokument) -> None:
        if dokument.page <= seiten_ohne_nummer:
            return
        canvas.saveState()
        canvas.setFont("Times-Italic", 9)
        canvas.setFillColor(colors.HexColor("#6b5a4a"))
        breite, _ = A5
        canvas.drawCentredString(breite / 2, 1.4 * cm, str(dokument.page - seiten_ohne_nummer))
        canvas.restoreState()
    return zeichnen


def buch_pdf_erzeugen(geruest_text: str, epoche: str | None, kapitel: list[tuple[int, str]],
                       cover_bytes: bytes | None = None) -> bytes:
    """kapitel: Liste von (Kapitelnummer, Kapiteltext), in Lesereihenfolge.
    cover_bytes: optionales, per Bildgenerierung erzeugtes Deckblattbild
    (siehe app/core/bild_generierung.py) - wird als eigene Seite vor der
    bisherigen Titelseite eingefuegt. None (Standard) erzeugt weiterhin ein
    PDF ohne Bildseite, unveraendert zum bisherigen Verhalten."""
    titel = titel_erkennen(geruest_text) or "Ohne Titel"
    titelseite = titelseite_erzeugen(geruest_text, epoche)
    untertitel_treffer = _UNTERTITEL_ZEILE_RE.search(titelseite)
    untertitel = untertitel_treffer.group(1).strip() if untertitel_treffer else None

    puffer = io.BytesIO()
    seitenrand = 2.4 * cm
    dokument = BaseDocTemplate(
        puffer, pagesize=A5,
        leftMargin=seitenrand, rightMargin=seitenrand,
        topMargin=2.6 * cm, bottomMargin=2.2 * cm,
        title=titel, author="Geschichten Erzähler",
    )
    rahmen = Frame(dokument.leftMargin, dokument.bottomMargin, dokument.width, dokument.height, id="inhalt")
    seiten_ohne_nummer = 2 if cover_bytes else 1
    dokument.addPageTemplates(
        [PageTemplate(id="seite", frames=[rahmen], onPage=_seitenzahl_zeichner(seiten_ohne_nummer))]
    )

    akzent = colors.HexColor("#7a4a2f")
    dunkel = colors.HexColor("#2b2118")
    gedaempft = colors.HexColor("#8a7a68")

    titel_stil = ParagraphStyle(
        "BuchTitel", fontName="Times-Bold", fontSize=26, leading=32,
        alignment=TA_CENTER, textColor=dunkel, spaceAfter=14,
    )
    untertitel_stil = ParagraphStyle(
        "BuchUntertitel", fontName="Times-Italic", fontSize=12.5, leading=17,
        alignment=TA_CENTER, textColor=akzent, spaceAfter=6,
    )
    zierstil = ParagraphStyle(
        "Zierzeichen", fontName="Times-Roman", fontSize=16,
        alignment=TA_CENTER, textColor=akzent, spaceBefore=10, spaceAfter=10,
    )
    fussnotiz_stil = ParagraphStyle(
        "Fussnotiz", fontName="Times-Roman", fontSize=9.5, leading=13,
        alignment=TA_CENTER, textColor=gedaempft, spaceBefore=6,
    )
    kapitel_nummer_stil = ParagraphStyle(
        "KapitelNummer", fontName="Times-Roman", fontSize=10.5, leading=14,
        alignment=TA_CENTER, textColor=akzent, spaceBefore=4, spaceAfter=2,
    )
    kapitel_titel_stil = ParagraphStyle(
        "KapitelTitel", fontName="Times-Bold", fontSize=16, leading=21,
        alignment=TA_CENTER, textColor=dunkel, spaceAfter=22,
    )
    absatz_stil = ParagraphStyle(
        "Absatz", fontName="Times-Roman", fontSize=10.5, leading=16,
        alignment=TA_JUSTIFY, firstLineIndent=14, spaceAfter=7,
        textColor=colors.HexColor("#1c1712"),
    )

    inhalt: list = []

    if cover_bytes:
        # Seitenfuellend, aber seitenverhaeltnistreu skaliert (das Bild ist
        # quadratisch, der Seiteninhaltsbereich nicht - eine Streckung auf
        # exakt dokument.width x dokument.height wuerde es verzerren).
        bild_breite, bild_hoehe = ImageReader(io.BytesIO(cover_bytes)).getSize()
        skalierung = min(dokument.width / bild_breite, dokument.height / bild_hoehe)
        cover = Image(
            io.BytesIO(cover_bytes),
            width=bild_breite * skalierung,
            height=bild_hoehe * skalierung,
        )
        cover.hAlign = "CENTER"
        inhalt.append(cover)
        inhalt.append(PageBreak())

    inhalt.append(Spacer(1, 4.2 * cm))
    inhalt.append(Paragraph(ZIERZEICHEN, zierstil))
    inhalt.append(Paragraph(_escape(titel), titel_stil))
    if untertitel:
        inhalt.append(Paragraph(_escape(untertitel), untertitel_stil))
    inhalt.append(Paragraph(ZIERZEICHEN, zierstil))
    inhalt.append(Paragraph("Erzählt von einer künstlichen Intelligenz", fussnotiz_stil))

    for nummer, text in kapitel:
        inhalt.append(PageBreak())
        untertitel_kapitel, absaetze = _kapitel_parsen(text)
        inhalt.append(Spacer(1, 1.6 * cm))
        inhalt.append(Paragraph(ZIERZEICHEN, zierstil))
        inhalt.append(Paragraph(f"KAPITEL {_roemisch(nummer)}", kapitel_nummer_stil))
        if untertitel_kapitel:
            inhalt.append(Paragraph(_escape(untertitel_kapitel), kapitel_titel_stil))
        for absatz in absaetze:
            inhalt.append(Paragraph(_escape(absatz), absatz_stil))

    dokument.build(inhalt)
    return puffer.getvalue()
