"""Erzeugt ein gestaltetes Buch-PDF aus den Kapiteldateien eines Projekts -
fuer den "PDF herunterladen"-Knopf im Stand & Export-Tab. Reine Formatierung
auf Basis der bereits vorhandenen Kapiteltexte, kein Ollama-Aufruf hier.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, Image, PageBreak, PageTemplate, Paragraph, Spacer

from app.core.geruest import titel_erkennen, titelseite_erzeugen

# Die eingebauten reportlab-Kernschriften (Times-Roman u.a.) sind an
# WinAnsiEncoding gebunden und koennen nur die ~256 Latin-1-Zeichen
# darstellen - Sonderzeichen wie "ō" (japanisches Makron, z.B. Figurenname
# "Genzō") werden dabei NICHT etwa als "?" angezeigt, sondern reportlab
# ersetzt sie still durch ein voellig unpassendes Symbol aus der internen
# ZapfDingbats-Fallback-Schrift. DejaVu Serif deckt als volle Unicode-Schrift
# auch Latin Extended-A/B, Griechisch, Kyrillisch usw. ab und wird deshalb
# hier fest eingebettet (Bitstream-Vera-Lizenz, frei redistributierbar).
_FONT_VERZEICHNIS = Path(__file__).resolve().parent.parent / "data" / "fonts"
_SCHRIFT_NORMAL = "DejaVuSerif"
_SCHRIFT_FETT = "DejaVuSerif-Bold"
_SCHRIFT_KURSIV = "DejaVuSerif-Italic"
_SCHRIFT_FETT_KURSIV = "DejaVuSerif-BoldItalic"

if _SCHRIFT_NORMAL not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(_SCHRIFT_NORMAL, str(_FONT_VERZEICHNIS / "DejaVuSerif.ttf")))
    pdfmetrics.registerFont(TTFont(_SCHRIFT_FETT, str(_FONT_VERZEICHNIS / "DejaVuSerif-Bold.ttf")))
    pdfmetrics.registerFont(TTFont(_SCHRIFT_KURSIV, str(_FONT_VERZEICHNIS / "DejaVuSerif-Italic.ttf")))
    pdfmetrics.registerFont(TTFont(_SCHRIFT_FETT_KURSIV, str(_FONT_VERZEICHNIS / "DejaVuSerif-BoldItalic.ttf")))
    pdfmetrics.registerFontFamily(
        _SCHRIFT_NORMAL, normal=_SCHRIFT_NORMAL, bold=_SCHRIFT_FETT,
        italic=_SCHRIFT_KURSIV, boldItalic=_SCHRIFT_FETT_KURSIV,
    )

_UNTERTITEL_ZEILE_RE = re.compile(r"^\*(.+?)\*\s*$", re.MULTILINE)

# Die Kapitelueberschrift-Zeile, die JEDE Kapiteldatei einleitet (Format
# laut Autor-Persona: "Kapitel eins: Sprechender Untertitel"). Das Modell
# setzt sie nicht zuverlaessig in reinem Text - mal in Markdown-Fett
# ("**...**"), mal als Markdown-Ueberschrift ("### Kapitel eins: ..."), und
# gelegentlich stehen sogar zwei solche Zeilen direkt hintereinander (eine
# vom Sicherheitsnetz ergaenzte Klartext-Zeile plus die rohe des Modells).
# Die Erkennung muss alle Varianten abdecken, sonst wird die Ueberschrift
# als gewoehnlicher Absatz mitgerendert (linksbuendig, falsche Schrift, und
# der Kapitelname erscheint doppelt).
_KAPITEL_UEBERSCHRIFT_RE = re.compile(
    r"^(?:#{1,6}\s*)?\*{0,2}Kapitel\s+\S+\s*[:\-–—]\s*(.+?)\*{0,2}\s*$", re.IGNORECASE
)


def _kapitel_parsen(text: str) -> tuple[str | None, list[str]]:
    """Trennt eine Kapiteldatei in (Kapitel-Untertitel, Absaetze). Ueberspringt
    die Titelseiten-Zeilen ("# Titel", "*Untertitel*"), die nur in Kapitel 1
    vorkommen (siehe geruest.titelseite_erzeugen), und erkennt die
    "Kapitel N: ..."-Ueberschrift, die jede Kapiteldatei einleitet."""
    zeilen = text.strip().split("\n")
    rest_start = len(zeilen)
    untertitel: str | None = None
    for i, zeile in enumerate(zeilen):
        z = zeile.strip()
        if not z:
            continue
        if z.startswith("# ") or (z.startswith("*") and z.endswith("*") and not z.startswith("**")):
            continue
        treffer = _KAPITEL_UEBERSCHRIFT_RE.match(z)
        if treffer:
            # Ersten Untertitel merken, jede weitere direkt folgende
            # Ueberschriftszeile aber ebenfalls verschlucken - sonst landet
            # eine doppelte "### Kapitel eins: ..."-Zeile als Absatz im Text.
            if untertitel is None:
                untertitel = treffer.group(1).strip()
            continue
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
        canvas.setFont(_SCHRIFT_KURSIV, 9)
        canvas.setFillColor(colors.HexColor("#6b5a4a"))
        breite, _ = A5
        canvas.drawCentredString(breite / 2, 1.4 * cm, str(dokument.page - seiten_ohne_nummer))
        canvas.restoreState()
    return zeichnen


def buch_pdf_erzeugen(geruest_text: str, epoche: str | None, kapitel: list[tuple[int, str]],
                       cover_bytes: bytes | None = None, einleitungssatz_vorlage: str | None = None) -> bytes:
    """kapitel: Liste von (Kapitelnummer, Kapiteltext), in Lesereihenfolge.
    cover_bytes: optionales, per Bildgenerierung erzeugtes Deckblattbild
    (siehe app/core/bild_generierung.py) - wird als eigene Seite vor der
    bisherigen Titelseite eingefuegt. None (Standard) erzeugt weiterhin ein
    PDF ohne Bildseite, unveraendert zum bisherigen Verhalten.
    einleitungssatz_vorlage siehe app/core/geruest.py:titelseite_erzeugen."""
    titel = titel_erkennen(geruest_text) or "Ohne Titel"
    titelseite = titelseite_erzeugen(geruest_text, epoche, einleitungssatz_vorlage)
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
    # Padding explizit auf 0 (Frame haette sonst reportlab-Default 6pt auf
    # allen vier Seiten) - die Cover-Skalierung unten rechnet bewusst gegen
    # die vollen dokument.width/height als nutzbaren Seiteninhaltsbereich;
    # mit dem Default-Padding waere der Rahmen innen 12pt schmaler/niedriger
    # als angenommen, wodurch ein bis an die Kante skaliertes (v.a. hochfor-
    # matiges) Cover einen LayoutError ausloest ("Flowable ... too large"),
    # weil das Bild selbst dann noch genau diese 12pt zu gross fuers
    # tatsaechlich verfuegbare Innenmass des Frames ist.
    rahmen = Frame(
        dokument.leftMargin, dokument.bottomMargin, dokument.width, dokument.height, id="inhalt",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    seiten_ohne_nummer = 2 if cover_bytes else 1
    dokument.addPageTemplates(
        [PageTemplate(id="seite", frames=[rahmen], onPage=_seitenzahl_zeichner(seiten_ohne_nummer))]
    )

    akzent = colors.HexColor("#7a4a2f")
    dunkel = colors.HexColor("#2b2118")
    gedaempft = colors.HexColor("#8a7a68")

    titel_stil = ParagraphStyle(
        "BuchTitel", fontName=_SCHRIFT_FETT, fontSize=26, leading=32,
        alignment=TA_CENTER, textColor=dunkel, spaceAfter=14,
    )
    untertitel_stil = ParagraphStyle(
        "BuchUntertitel", fontName=_SCHRIFT_KURSIV, fontSize=12.5, leading=17,
        alignment=TA_CENTER, textColor=akzent, spaceAfter=6,
    )
    fussnotiz_stil = ParagraphStyle(
        "Fussnotiz", fontName=_SCHRIFT_NORMAL, fontSize=9.5, leading=13,
        alignment=TA_CENTER, textColor=gedaempft, spaceBefore=6,
    )
    kapitel_nummer_stil = ParagraphStyle(
        "KapitelNummer", fontName=_SCHRIFT_NORMAL, fontSize=10.5, leading=14,
        alignment=TA_CENTER, textColor=akzent, spaceBefore=4, spaceAfter=2,
    )
    kapitel_titel_stil = ParagraphStyle(
        "KapitelTitel", fontName=_SCHRIFT_FETT, fontSize=16, leading=21,
        alignment=TA_CENTER, textColor=dunkel, spaceAfter=22,
    )
    absatz_stil = ParagraphStyle(
        "Absatz", fontName=_SCHRIFT_NORMAL, fontSize=10.5, leading=16,
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
    inhalt.append(Paragraph(_escape(titel), titel_stil))
    if untertitel:
        inhalt.append(Paragraph(_escape(untertitel), untertitel_stil))
    inhalt.append(Paragraph("Erzählt von einer künstlichen Intelligenz", fussnotiz_stil))

    for nummer, text in kapitel:
        inhalt.append(PageBreak())
        untertitel_kapitel, absaetze = _kapitel_parsen(text)
        inhalt.append(Spacer(1, 1.6 * cm))
        inhalt.append(Paragraph(f"KAPITEL {_roemisch(nummer)}", kapitel_nummer_stil))
        if untertitel_kapitel:
            inhalt.append(Paragraph(_escape(untertitel_kapitel), kapitel_titel_stil))
        for absatz in absaetze:
            inhalt.append(Paragraph(_escape(absatz), absatz_stil))

    dokument.build(inhalt)
    return puffer.getvalue()
