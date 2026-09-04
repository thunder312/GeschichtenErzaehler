"""Dateizugriff auf Projektordner - portiert aus pre-GUI/novelle.py.

Haelt den Ordnervertrag aus doc/Schnittstellen-Uebersicht.md Abschnitt 1
exakt ein, damit ein mit der GUI erzeugter Projektordner unveraendert mit
der bestehenden novelle.py weiterbearbeitet werden koennte (und umgekehrt).

Unterschied zum CLI: Dort ist der Projektordner das aktuelle Arbeits-
verzeichnis (PROJEKT = Path(cwd)/"projekt"). Die GUI verwaltet mehrere
Projekte parallel, deshalb nehmen alle Funktionen hier den Projektordner
explizit als Parameter entgegen statt ihn aus einer globalen Konstante zu
lesen.
"""
from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path

from app.core import epoche as _epoche
from app.core import geruest as _geruest
from app.core.textutil import woerter

logger = logging.getLogger(__name__)

EPOCHE_PERSONA_DATEIEN = ("architekt.txt", "autor.txt", "pruefer_anachronismus.txt")
GEMEINSAME_PERSONA_DATEIEN = (
    "chronist.txt", "pruefer_kontinuitaet.txt", "lektor.txt", "pruefer_satzbau.txt",
)


class DateiFehlt(Exception):
    pass


def kapitel_datei(projekt: Path, n: int) -> Path:
    return projekt / f"kapitel_{n:02d}.md"


def stand_datei(projekt: Path, n: int) -> Path:
    return projekt / f"stand_{n:02d}.md"


def befunde_datei(projekt: Path, n: int) -> Path:
    return projekt / f"befunde_{n:02d}.json"


def abgelehnte_befunde_datei(projekt: Path) -> Path:
    """Vom Nutzer dauerhaft abgelehnte Pruefer-Vorschlaege (Button
    "Ablehnen" im Tab "Pruefen & Anwenden", siehe
    app/core/befunde_ablehnung.py) - PROJEKTWEIT statt pro Kapitel, damit
    z.B. eine in einer FanFic-Epoche bewusst gewuenschte Kanon-Abweichung
    (andere Figuren/Orte als im Original) nicht in jedem Kapitel einzeln
    abgelehnt werden muss."""
    return projekt / "abgelehnte_befunde.json"


def geruest_datei(projekt: Path) -> Path:
    return projekt / "geruest.md"


def cover_datei(projekt: Path) -> Path:
    return projekt / "cover.png"


def cover_log_datei(projekt: Path) -> Path:
    """Metadaten (Zeitstempel, Prompt, Kommentar) aller bisherigen Titelbild-
    Versuche dieses Projekts, siehe app/core/cover_log.py - die eigentlichen
    Bild-Bytes je Versuch liegen separat unter cover_log_bild_datei(), damit
    diese Datei klein bleibt."""
    return projekt / "cover_log.json"


def cover_log_bild_datei(projekt: Path, eintrag_id: str) -> Path:
    return projekt / "cover_log" / f"{eintrag_id}.png"


def verbotsliste_datei(projekt: Path) -> Path:
    return projekt / "verbotsliste.md"


def einleitungssatz_datei(projekt: Path) -> Path:
    """Projekt-eigene Kopie von epochen/<Epoche>/einleitungssatz.txt (siehe
    projekt_anlegen()) - die Satzvorlage fuer die Titelseiten-Zeile in
    Kapitel 1 (siehe app/core/geruest.py:titelseite_erzeugen). Wie
    verbotsliste_datei() eine eigene, von der zentralen Epochen-Bibliothek
    unabhaengige Kopie, damit sie sich auch nachtraeglich je Projekt von
    Hand korrigieren laesst (z.B. wenn die Epoche-Vorlage grammatikalisch
    falsch war, als das Projekt angelegt wurde)."""
    return projekt / "einleitungssatz.txt"


def stilproben_datei(projekt: Path) -> Path:
    """Optionale, vom Nutzer gepflegte Sammlung kurzer Vorbild-Ausschnitte
    (siehe app/api/pipeline.py:_autor_system_prompt) - anders als
    verbotsliste_datei() gibt es dafuer KEINE Epoche-Vorlage zum Kopieren,
    die Datei existiert nur, wenn der Nutzer sie ueber den Geruest-Tab
    selbst befuellt hat. Ein leeres/fehlendes stilproben.md aendert am
    Autor-Prompt nichts."""
    return projekt / "stilproben.md"


def architekt_verlauf_datei(projekt: Path) -> Path:
    """Zwischenspeicher fuer ein unterbrochenes Architekten-Gespraech (siehe
    app/api/architekt.py) - existiert nur, waehrend das Interview noch
    laeuft, und wird bei Abschluss oder explizitem Abbruch wieder
    geloescht."""
    return projekt / "architekt_verlauf.json"


def lies(pfad: Path, pflicht: bool = True, ersatz: str = "") -> str:
    if not pfad.exists():
        if pflicht:
            raise DateiFehlt(f"Datei fehlt: {pfad}")
        return ersatz
    return pfad.read_text(encoding="utf-8").strip()


def schreib(pfad: Path, text: str, force: bool = False) -> tuple[Path, str | None]:
    """Schreibt die Datei, sichert eine vorhandene Fassung als .bak (ausser
    force=True). Gibt (Pfad, Name_der_Sicherung_oder_None) zurueck."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    sicherung_name = None
    if pfad.exists() and not force:
        sicherung = pfad.with_suffix(pfad.suffix + f".{int(time.time())}.bak")
        pfad.rename(sicherung)
        sicherung_name = sicherung.name
    pfad.write_text(text + "\n", encoding="utf-8")
    return pfad, sicherung_name


def kapitelnummer_aus_dateiname(pfad: Path) -> int:
    treffer = re.search(r"kapitel_(\d+)\.md$", pfad.name)
    return int(treffer.group(1)) if treffer else -1


def vorhandene_kapitel(projekt: Path) -> list[Path]:
    return sorted(projekt.glob("kapitel_*.md"), key=kapitelnummer_aus_dateiname)


def persona_lesen(projekt: Path, name: str) -> str:
    return lies(projekt / "personas" / f"{name}.txt")


def projekt_anlegen(ziel: Path, epoche_ordner: Path, gemeinsame_personas_ordner: Path,
                     epoche_name: str, zweite_epoche_ordner: Path | None = None,
                     zweite_epoche_name: str | None = None) -> None:
    """Legt personas/ + projekt/ in ziel an, analog zu novelle.py's
    _projekt_befuellen(). ziel muss bereits existieren oder wird erzeugt.

    Mit zweite_epoche_ordner/zweite_epoche_name (Zeitsprung-Projekt, siehe
    app/core/epoche.py:zeitsprung_dateien_zusammenfuehren) werden Architekt-/
    Autor-/Anachronismus-Persona und Verbotsliste im Anschluss um eine
    Referenz auf die zweite Epoche erweitert - beide Epochen bleiben dabei
    unveraendert in der zentralen Bibliothek, nur die frisch kopierten
    Projekt-Dateien werden angereichert."""
    ziel.mkdir(parents=True, exist_ok=True)
    personas_ziel = ziel / "personas"
    personas_ziel.mkdir(exist_ok=True)
    (ziel / "projekt").mkdir(exist_ok=True)

    for datei in EPOCHE_PERSONA_DATEIEN:
        quelle = epoche_ordner / datei
        if quelle.exists():
            shutil.copy(quelle, personas_ziel / datei)
    for datei in GEMEINSAME_PERSONA_DATEIEN:
        quelle = gemeinsame_personas_ordner / datei
        if quelle.exists():
            shutil.copy(quelle, personas_ziel / datei)

    verbotsliste_ziel = ziel / "projekt" / "verbotsliste.md"
    verbotsliste_quelle = epoche_ordner / "verbotsliste.md"
    if verbotsliste_quelle.exists():
        shutil.copy(verbotsliste_quelle, verbotsliste_ziel)

    einleitungssatz_quelle = epoche_ordner / "einleitungssatz.txt"
    if einleitungssatz_quelle.exists():
        shutil.copy(einleitungssatz_quelle, einleitungssatz_datei(ziel / "projekt"))

    if zweite_epoche_ordner is not None and zweite_epoche_name is not None:
        primaer_dateien = {datei: lies(personas_ziel / datei, pflicht=False, ersatz="")
                            for datei in EPOCHE_PERSONA_DATEIEN}
        primaer_dateien["verbotsliste.md"] = lies(verbotsliste_ziel, pflicht=False, ersatz="")
        sekundaer_dateien = {datei: lies(zweite_epoche_ordner / datei, pflicht=False, ersatz="")
                             for datei in EPOCHE_PERSONA_DATEIEN}
        sekundaer_dateien["verbotsliste.md"] = lies(zweite_epoche_ordner / "verbotsliste.md", pflicht=False, ersatz="")

        zusammengefuehrt = _epoche.zeitsprung_dateien_zusammenfuehren(
            epoche_name, primaer_dateien, zweite_epoche_name, sekundaer_dateien,
        )
        for datei in EPOCHE_PERSONA_DATEIEN:
            if zusammengefuehrt.get(datei):
                (personas_ziel / datei).write_text(zusammengefuehrt[datei].strip() + "\n", encoding="utf-8")
        if zusammengefuehrt.get("verbotsliste.md"):
            verbotsliste_ziel.write_text(zusammengefuehrt["verbotsliste.md"].strip() + "\n", encoding="utf-8")

        (ziel / ".epoche_zweite").write_text(zweite_epoche_name, encoding="utf-8")

    (ziel / ".epoche").write_text(epoche_name, encoding="utf-8")


def epoche_von_projekt(ziel: Path) -> str | None:
    marker = ziel / ".epoche"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def epoche_setzen(ziel: Path, epoche_name: str) -> None:
    """Aendert die Epoche-Zuordnung eines BESTEHENDEN Projekts (siehe
    app/api/projects.py:projekt_epoche_aendern, Drag&Drop in der Ordner-
    Ansicht) - schreibt NUR den Marker, personas/ und verbotsliste.md
    bleiben unangetastet (waren beim Anlegen einmalig aus der alten Epoche
    kopiert worden, siehe projekt_anlegen() oben, und wuerden sich sonst
    unbemerkt mitten in einer laufenden Geschichte aendern)."""
    (ziel / ".epoche").write_text(epoche_name, encoding="utf-8")


def zweite_epoche_von_projekt(ziel: Path) -> str | None:
    """Siehe projekt_anlegen() - nur gesetzt bei einem Zeitsprung-Projekt."""
    marker = ziel / ".epoche_zweite"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def woerter_im_kapitel(projekt: Path, n: int) -> int:
    text = lies(kapitel_datei(projekt, n), pflicht=False, ersatz="")
    return woerter(text)


def _freier_pfad(wurzel: Path, name: str) -> Path:
    """Findet einen im Ordner `wurzel` noch freien Namen, ausgehend von
    `name` - haengt bei Kollision -2, -3, ... an (z.B. wenn bereits ein
    Projekt mit demselben aus dem Titel abgeleiteten Namen existiert)."""
    ziel = wurzel / name
    zaehler = 2
    while ziel.exists():
        ziel = wurzel / f"{name}-{zaehler}"
        zaehler += 1
    return ziel


def _v2_pfad(quelle: Path) -> Path:
    """Zielordner fuers Duplizieren beim 'Neu schreiben'-Feature (siehe
    app/api/projects.py:projekt_neu_schreiben) - haengt '_v2' an den
    Ordnernamen an, bei Kollision '_v3', '_v4', ... statt '_v2' erneut zu
    versuchen."""
    version = 2
    ziel = quelle.parent / f"{quelle.name}_v{version}"
    while ziel.exists():
        version += 1
        ziel = quelle.parent / f"{quelle.name}_v{version}"
    return ziel


def standnummer_aus_dateiname(pfad: Path) -> int:
    treffer = re.search(r"stand_(\d+)\.md$", pfad.name)
    return int(treffer.group(1)) if treffer else -1


def projekt_bereinigen(projekt_root: Path) -> dict[str, int]:
    """Raeumt ein fertig geprueftes Projekt auf ("Projekt bereinigen"-Dialog
    beim Abschliessen der Pruefung, siehe app/api/projects.py und
    frontend/src/pages/PruefenAnwendenPage.tsx). Loescht:
    - JEDE .bak-Sicherung (siehe schreib() oben), egal ob unter projekt/
      oder personas/ - Editier-Historie einzelner Dateien, die nach
      abgeschlossener Pruefung keinen Wert mehr hat.
    - ALLE stand_NN.md ausser dem mit der hoechsten Nummer - die frueheren
      dienten nur als Zwischenschritt beim sequentiellen Schreiben (jedes
      Kapitel bekommt beim Schreiben nur den Stand SEINES Vorgaengers als
      Kontext, siehe app/api/pipeline.py:_kapitel_schreiben_kern), fuer eine
      fertige Geschichte hat nur der letzte noch Bedeutung (z.B. als
      Ausgangspunkt fuer eine spaetere Fortsetzung).

    Kapitel-Dateien (kapitel_NN.md) sowie geruest.md/verbotsliste.md/
    einleitungssatz.txt/stilproben.md/personas/ bleiben unangetastet - die
    Kapitel sind die einzige dauerhafte Kopie des fertigen Texts (PDF-Export
    laeuft nur on-the-fly aus ihnen, siehe app/core/pdf_export.py), die
    uebrigen sind entweder klein oder fuer ein spaeteres "Neu schreiben"
    noetig (siehe _NEUSCHREIBEN_AUSGANGSDATEIEN oben)."""
    geloeschte_bak = 0
    for bak in projekt_root.rglob("*.bak"):
        bak.unlink()
        geloeschte_bak += 1

    geloeschte_stand = 0
    stand_dateien = sorted(projekt_root.glob("projekt/stand_*.md"), key=standnummer_aus_dateiname)
    for alt in stand_dateien[:-1]:
        alt.unlink()
        geloeschte_stand += 1

    return {"geloeschte_bak": geloeschte_bak, "geloeschte_stand": geloeschte_stand}


_NEUSCHREIBEN_AUSGANGSDATEIEN = ("verbotsliste.md", "geruest.md", "stand_00.md", "einleitungssatz.txt")

# Marker im Duplikat-Ordner, siehe projekt_fuer_neuschreiben_duplizieren()/
# neuschreiben_quelle() unten. Gleiches Muster wie ".epoche" oben: einfache
# Klartext-Datei mit genau einem Wert.
_NEUSCHREIBEN_MARKER = ".neu_geschrieben_aus"


def projekt_fuer_neuschreiben_duplizieren(quelle: Path, quelle_ordner: str) -> Path:
    """Legt fuers 'Neu schreiben'-Feature (Icon in der Projektliste, siehe
    app/api/projects.py:projekt_neu_schreiben) ein frisches Duplikat an
    (Ordnername + '_v2') - bewusst KEIN voller Ordner-Kopie+Aufraeumen mehr
    (wie fruecher per shutil.copytree), sondern von vornherein nur die fuers
    Weiterschreiben noetigen Ausgangsdaten:
    - personas/ 1:1 vom Quellprojekt (architekt.txt/autor.txt/... werden
      von persona_lesen() ohne Fallback aus dem Projektordner gelesen -
      ohne die Dateien waere das Duplikat funktionsunfaehig).
    - .epoche/.epoche_zweite (Marker, siehe epoche_von_projekt()).
    - aus projekt/ NUR verbotsliste.md, geruest.md, stand_00.md - der
      Zustand direkt nach Abschluss des Architekten-Interviews, BEVOR
      irgendein Kapitel geschrieben wurde. Kapitel/Stand-Folgedateien/
      Befunde/Automatik-Status/Cover/Stilproben entstehen erst durchs
      Schreiben/Pruefen und werden deshalb gar nicht erst kopiert.

    `quelle_ordner` ist der Ordnerpfad des Quellprojekts relativ zur
    Projekte-Wurzel (siehe ProjektKurz.ordner, vom Aufrufer schon bekannt) -
    landet unveraendert im ".neu_geschrieben_aus"-Marker im Duplikat, damit
    die Projektuebersicht ein per "Neu schreiben" erzeugtes Duplikat von
    seinem gleichnamigen Original unterscheiden kann (Titel/Gerüst werden
    ja 1:1 mitkopiert - ohne diesen Marker sehen beide Projekte in der Liste
    identisch aus, siehe _projekt_kurz() in app/api/projects.py).

    Anders als bisher wird der Automatikmodus danach NICHT mehr automatisch
    gestartet (siehe frontend/src/pages/ProjektePage.tsx) - das Duplikat
    landet im Gerüst-Tab, der Nutzer entscheidet selbst, ob/wann er
    weiterschreiben laesst."""
    ziel = _v2_pfad(quelle)
    ziel.mkdir(parents=True)
    (ziel / "projekt").mkdir()

    shutil.copytree(quelle / "personas", ziel / "personas", dirs_exist_ok=True)

    for marker in (".epoche", ".epoche_zweite"):
        quelle_marker = quelle / marker
        if quelle_marker.exists():
            shutil.copy(quelle_marker, ziel / marker)

    for name in _NEUSCHREIBEN_AUSGANGSDATEIEN:
        quelle_datei = quelle / "projekt" / name
        if quelle_datei.exists():
            shutil.copy(quelle_datei, ziel / "projekt" / name)

    (ziel / _NEUSCHREIBEN_MARKER).write_text(quelle_ordner, encoding="utf-8")

    return ziel


def projekt_zuruecksetzen(projekt_root: Path) -> dict[str, int]:
    """Setzt ein Projekt IN-PLACE auf den Zustand direkt nach dem Architekten-
    Interview zurueck (Button "Zurücksetzen" im Gerüst-Tab) - das Gegenstueck
    zu projekt_fuer_neuschreiben_duplizieren(), nur ohne Kopie: die
    bestehende Instanz wird ueberschrieben.

    Behalten werden personas/, die .epoche-Marker und aus projekt/ nur die
    _NEUSCHREIBEN_AUSGANGSDATEIEN (verbotsliste.md, geruest.md, stand_00.md,
    einleitungssatz.txt). Alles, was erst durchs Schreiben/Pruefen entsteht -
    Kapitel, Folge-Staende, Befunde, Automatik-Status/-Verlauf, abgelehnte
    Befunde, Cover, Stilproben, die Architekten-Gespraech-Mitschrift, der
    fertige Sammel-Export sowie jede .bak-Sicherung - wird geloescht.
    Unumkehrbar; der Aufrufer zeigt vorher einen Bestaetigungsdialog."""
    geloeschte_dateien = 0
    projekt_unterordner = projekt_root / "projekt"
    if projekt_unterordner.is_dir():
        for eintrag in projekt_unterordner.iterdir():
            if eintrag.name in _NEUSCHREIBEN_AUSGANGSDATEIEN:
                continue
            if eintrag.is_dir():
                shutil.rmtree(eintrag)
            else:
                eintrag.unlink()
            geloeschte_dateien += 1

    export = projekt_root / f"{projekt_root.name}.md"
    if export.exists():
        export.unlink()
        geloeschte_dateien += 1

    geloeschte_bak = 0
    for bak in projekt_root.rglob("*.bak"):
        bak.unlink()
        geloeschte_bak += 1

    return {"geloeschte_dateien": geloeschte_dateien, "geloeschte_bak": geloeschte_bak}


def neuschreiben_quelle(ziel: Path) -> str | None:
    """Nur gesetzt, wenn `ziel` per 'Neu schreiben' aus einem anderen
    Projekt dupliziert wurde (siehe projekt_fuer_neuschreiben_duplizieren())
    - liefert dann den Ordnerpfad des Quellprojekts relativ zur
    Projekte-Wurzel, sonst None. Das Quellprojekt kann inzwischen umbenannt
    oder geloescht worden sein - der Aufrufer entscheidet, wie er einen
    nicht mehr aufloesbaren Pfad anzeigt."""
    marker = ziel / _NEUSCHREIBEN_MARKER
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def _projektordner_rename_mit_retry(projekt_root: Path, neuer_pfad: Path) -> str | None:
    """Benennt den Projektordner um und gibt den neuen Namen zurueck, sonst
    None. Direkt nach dem Schreiben von geruest.md haelt ein Sync-Tool
    (Dropbox) oder der Windows-Suchindex/Virenscanner die Datei manchmal
    fuer einen kurzen Moment noch offen - Windows verweigert dann das
    Umbenennen des Elternordners mit PermissionError(13), obwohl der Zustand
    Millisekunden spaeter schon wieder frei ist. Mit kurzen, steigenden
    Wartezeiten erneut versuchen, bevor endgueltig aufgegeben wird
    (insgesamt ca. 3s), statt beim ersten Versuch schon klein beizugeben."""
    letzter_fehler: OSError | None = None
    for wartezeit in (0, 0.1, 0.2, 0.4, 0.8, 1.6):
        if wartezeit:
            time.sleep(wartezeit)
        try:
            projekt_root.rename(neuer_pfad)
            return neuer_pfad.name
        except OSError as e:
            letzter_fehler = e

    logger.warning(
        "Projektordner-Umbenennung fehlgeschlagen nach mehreren Versuchen: %s -> %s (%r)",
        projekt_root, neuer_pfad, letzter_fehler,
    )
    return None


def projektordner_umbenennen(projekt_root: Path, geruest_text: str) -> str | None:
    """Versucht, den Projektordner nach dem im Geruest gewaehlten Titel
    umzubenennen - portiert aus novelle.py's
    _projektordner_nach_titel_umbenennen(). Nur direkt nach dem
    Architekten-Gespraech sinnvoll, solange noch kein Kapitel existiert.
    Gibt den neuen Ordnernamen zurueck, falls umbenannt wurde, sonst None
    (kein Fehler - best effort, wie im Original)."""
    if vorhandene_kapitel(projekt_root / "projekt"):
        return None

    titel = _geruest.titel_erkennen(geruest_text)
    if not titel:
        return None

    neuer_name = _geruest.ordnername_aus_titel(titel)
    if projekt_root.name == neuer_name:
        return None

    neuer_pfad = _freier_pfad(projekt_root.parent, neuer_name)
    return _projektordner_rename_mit_retry(projekt_root, neuer_pfad)


class OrdnerUmbenennenFehler(Exception):
    """projektordner_manuell_umbenennen() - der Aufrufer (app/api/projects.py)
    uebersetzt das je nach `code` in eine 422 (ungueltige Eingabe) oder 409
    (Datei gesperrt, spaeter erneut versuchen)."""

    def __init__(self, nachricht: str, code: str) -> None:
        super().__init__(nachricht)
        self.code = code


def projektordner_manuell_umbenennen(projekt_root: Path, wunschname: str) -> str:
    """Explizites Umbenennen des Projektordners (Button "Ordner umbenennen" im
    Gerüst-Tab, siehe app/api/projects.py) - anders als
    projektordner_umbenennen() NICHT an "noch kein Kapitel geschrieben"
    gebunden und NICHT aus dem Titel abgeleitet, sondern vom Nutzer frei
    gewaehlt. Der Wunschname wird wie ein Titel zu einem dateisystem-
    tauglichen Slug normalisiert (ordnername_aus_titel: Umlaute -> ae/oe/ue,
    Leerzeichen -> "-", Sonderzeichen raus).

    Gibt den tatsaechlichen neuen Ordnernamen zurueck (nur das letzte
    Pfadsegment). Wirft OrdnerUmbenennenFehler:
    - code "leer"       - Wunschname leer / nur Sonderzeichen
    - code "unveraendert" - Slug identisch mit dem aktuellen Namen
    - code "gesperrt"   - Umbenennen dauerhaft fehlgeschlagen (Datei offen)
    """
    if not wunschname.strip():
        raise OrdnerUmbenennenFehler("Bitte einen Ordnernamen eingeben.", "leer")

    neuer_name = _geruest.ordnername_aus_titel(wunschname)
    # ordnername_aus_titel() faellt bei reinem Sonderzeichen-Input auf
    # "Neues-Projekt" zurueck - das ist hier kein sinnvolles Ergebnis.
    if not re.sub(r"[^A-Za-z0-9]", "", wunschname):
        raise OrdnerUmbenennenFehler(
            "Der Name enthält keine verwertbaren Buchstaben oder Ziffern.", "leer",
        )
    if neuer_name == projekt_root.name:
        raise OrdnerUmbenennenFehler(
            "Der Ordner heißt bereits so (nach Anpassung von Umlauten/Sonderzeichen).",
            "unveraendert",
        )

    neuer_pfad = _freier_pfad(projekt_root.parent, neuer_name)
    ergebnis = _projektordner_rename_mit_retry(projekt_root, neuer_pfad)
    if ergebnis is None:
        raise OrdnerUmbenennenFehler(
            "Der Projektordner konnte nicht umbenannt werden - vermutlich hält "
            "gerade ein anderes Programm (Dropbox, ein Editor, der Virenscanner) "
            "eine Datei darin offen. Bitte kurz warten und erneut versuchen.",
            "gesperrt",
        )
    return ergebnis
