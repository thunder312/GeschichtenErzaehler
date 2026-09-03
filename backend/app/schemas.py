"""Pydantic-Schemas fuer die REST-/WebSocket-API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EpocheKurz(BaseModel):
    # Ordner-/Identifier-Name - stabil, wird als Wert fuer die Epoche-Auswahl
    # beim Anlegen eines Projekts verwendet und landet 1:1 im ".epoche"-
    # Marker des Projekts (siehe app/core/projekt_dateien.py). AENDERT SICH
    # NICHT zwangslaeufig beim Umbenennen (siehe epoche_umbenennen()) - fuer
    # die Anzeige immer `anzeigename` verwenden, nie `name`.
    name: str
    # Frei editierbarer Anzeigename (".name"-Marker, siehe
    # app/api/projects.py:_epoche_anzeigename_lesen) - faellt ohne
    # gespeicherten Marker auf `name` mit Leerzeichen statt "-" zurueck.
    anzeigename: str
    genre: str | None = None
    # Hex-Farbcode (z.B. "#a16207") fuer die farbige Markierung in der
    # Projektliste (siehe app/api/epochen.py:epoche_farbe_schreiben) -
    # None, solange fuer diese Epoche noch keine Farbe gesetzt wurde.
    farbe: str | None = None


class EpocheErstellenAnfrage(BaseModel):
    name: str = Field(min_length=1)
    genre: str = ""
    erfunden: bool
    beschreibung: str = Field(min_length=1)
    zeitraum: str = Field(min_length=1)
    orte: str = Field(min_length=1)
    gesellschaft: str = Field(min_length=1)
    statusregel: str = Field(min_length=1)
    rang_wort: str = ""
    anreden: str = ""
    nebenstrang_typen: str = ""
    vorbild_franchise: str = ""
    verbote_start: str = ""


class EpocheErstellenAntwort(BaseModel):
    name: str
    ordner: str
    dateien: dict[str, str]


class EpocheDateiSchreibenAnfrage(BaseModel):
    inhalt: str


class EpocheGenreAnfrage(BaseModel):
    genre: str = ""


class EpocheFarbeAnfrage(BaseModel):
    farbe: str = ""


class EpocheNameAnfrage(BaseModel):
    name: str = Field(min_length=1)


class EpocheUmbenennenAntwort(BaseModel):
    # Neuer Ordner-/Identifier-Name (nur veraendert, wenn der physische
    # Ordner mitgezogen werden konnte, siehe epoche_umbenennen()).
    ordner: str
    anzeigename: str
    # Anzahl bereits bestehender Projekte (aller Benutzer), deren
    # ".epoche"/".epoche_zweite"-Marker dabei auf den neuen Ordnernamen
    # nachgezogen wurden - nur > 0, wenn sich `ordner` tatsaechlich
    # geaendert hat.
    aktualisierte_projekte: int


class ProjektKurz(BaseModel):
    ordner: str
    titel: str | None = None
    epoche: str | None = None
    # Nur gesetzt bei einem Zeitsprung-Projekt (siehe ProjektAnlegenAnfrage.
    # zweite_epoche) - zweite, per Zeitsprung erreichte Epoche.
    zweite_epoche: str | None = None
    anzahl_kapitel: int
    letztes_geplantes_kapitel: int | None = None
    # None = Automatikmodus nie gestartet. Siehe app/core/automatik.py:
    # zustand_zusammenfassen() fuer die moeglichen Werte.
    automatik_zustand: str | None = None
    # Nur gesetzt, wenn dieses Projekt per "Neu schreiben" aus einem anderen
    # dupliziert wurde (siehe app/core/projekt_dateien.py:neuschreiben_quelle())
    # - Ordnerpfad des Quellprojekts, fuer die Unterscheidung gleichnamiger
    # Projekte in der Uebersicht (Titel/Gerüst werden 1:1 mitkopiert).
    neu_geschrieben_aus: str | None = None
    # "YYYY-MM-DD HH:MM", Anlage-Zeitpunkt des Projektordners (Dateisystem-
    # Erstellungszeit - siehe app/api/projects.py:_projekt_kurz).
    erstellt_am: str | None = None
    # "YYYY-MM-DD HH:MM", letzte Aenderung an geruest.md - faellt auf den
    # Projektordner selbst zurueck, solange geruest.md noch nicht existiert
    # (Projekt angelegt, Architekten-Interview aber noch nicht abgeschlossen).
    zuletzt_bearbeitet_am: str | None = None


class ProjektEpocheAnfrage(BaseModel):
    # Ordner-/Identifier-Name der Ziel-Epoche (siehe EpocheKurz.name) - NICHT
    # der Anzeigename, siehe app/api/projects.py:projekt_epoche_aendern.
    epoche: str = Field(min_length=1)


class ProjektAnlegenAnfrage(BaseModel):
    # Leer erlaubt: der Titel ergibt sich haeufig erst aus dem Architekten-
    # Interview - siehe projekt_anlegen() in app/api/projects.py, das dann
    # ersatzweise den Platzhalter-Ordnernamen "neu" verwendet.
    titel: str = ""
    epoche: str
    # Optional: zweite, bereits existierende Epoche fuer eine Zeitsprung-
    # Geschichte (Zeitreise-Geraet, Ritual, o.ae.) - siehe
    # app/core/epoche.py:zeitsprung_dateien_zusammenfuehren.
    zweite_epoche: str | None = None


class ProjektDetail(BaseModel):
    ordner: str
    epoche: str | None
    zweite_epoche: str | None = None
    geruest: str | None
    verbotsliste: str | None
    stilproben: str | None
    kapitel: list[int]
    jahr: str | None = None
    jugendschutz_stufe: str | None = None
    autor_modell: str | None = None
    automatische_fortsetzung: bool | None = None
    letztes_geplantes_kapitel: int | None = None
    kapitelplan: dict[int, int] = {}


class GeruestSchreibenAnfrage(BaseModel):
    inhalt: str


class SchreibenAnfrage(BaseModel):
    zusatzhinweis: str = ""
    ssh_ziel_id: str | None = None


class SSHZielAnlegenAnfrage(BaseModel):
    name: str = Field(min_length=1)
    # Fuer auth_method='direct' enthaelt 'host' die komplette Basis-URL
    # (z.B. 'http://192.168.1.50:11434') statt eines SSH-Hostnamens -
    # username/port/remote_ollama_port bleiben dann unbenutzt.
    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = ""
    auth_method: Literal["password", "private_key", "agent", "direct"]
    password: str | None = None
    private_key_pem: str | None = None
    private_key_passphrase: str | None = None
    remote_ollama_port: int = Field(default=11434, ge=1, le=65535)
    # Port eines auf demselben Host laufenden sd-server (Bildgenerierung,
    # siehe app/core/bild_generierung.py) - None bedeutet: dieses KI-Ziel
    # bietet keine Bildgenerierung an.
    bildki_port: int | None = Field(default=None, ge=1, le=65535)


class SSHZielAntwort(BaseModel):
    id: str
    name: str
    host: str
    port: int
    username: str
    auth_method: str
    remote_ollama_port: int
    bildki_port: int | None = None
    favorit: bool
    created_at: str
    updated_at: str


class SSHZielFavoritAnfrage(BaseModel):
    favorit: bool


class SSHTestAnfrage(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = ""
    auth_method: Literal["password", "private_key", "agent", "direct"]
    password: str | None = None
    private_key_pem: str | None = None
    private_key_passphrase: str | None = None
    remote_ollama_port: int = Field(default=11434, ge=1, le=65535)


class SSHTestAntwort(BaseModel):
    erfolgreich: bool
    meldung: str


class OllamaModellInfo(BaseModel):
    name: str
    parameter_size: str | None = None
    size_bytes: int | None = None


class PersonaModellAntwort(BaseModel):
    persona: str
    default_modell: str
    override_modell: str | None
    effektives_modell: str


class PersonaModellSetzenAnfrage(BaseModel):
    modell: str | None = None


class Finding(BaseModel):
    code: str
    meldung: str
    schwere: str


class BefundBeschreibung(BaseModel):
    quelle: str
    text: str


class Befund(BaseModel):
    """Ein (ggf. aus mehreren Pruefer-Funden zusammengefuehrter) Fund - siehe
    app/core/befunde_merge.py fuer die Zusammenfuehrungs-Logik und
    app/core/fundstellen.py fuer die Ermittlung von start/end."""
    id: str
    kategorien: list[str]
    fundstelle: str
    beschreibungen: list[BefundBeschreibung]
    sicherheit: str | None
    vorschlag: str | None
    konflikt: bool
    konflikt_vorschlaege: list[BefundBeschreibung] | None = None
    gefunden: bool
    start: int | None
    end: int | None


class BefundAblehnenAnfrage(BaseModel):
    """Button "Ablehnen" im Tab "Pruefen & Anwenden" - siehe
    app/core/befunde_ablehnung.py. `befund_id` ist die id des Funds
    INNERHALB des zuletzt gespeicherten befunde_{n}.json (also OHNE das vom
    Frontend fuer die kapitelweite Anzeige vorangestellte "{n}-", siehe
    PruefenAnwendenPage.tsx:alleShiftedBefunde)."""
    befund_id: str


class BefundUebernehmenAnfrage(BaseModel):
    """Button "Übernehmen" in der Mobil-Ansicht (siehe MobilPage.tsx) -
    wendet EINEN Fund serverseitig an (Text-Splice + Speichern), OHNE dass
    dafuer ein Monaco-Editor im Browser laufen muss (siehe app/api/
    projects.py:befund_uebernehmen). `vorschlag_override` erlaubt eine
    leichte Abaenderung des Pruefer-Vorschlags vor dem Uebernehmen (Button
    "kleine Verbesserung" auf dem Handy) - None/leer nutzt den
    unveraenderten Original-Vorschlag."""
    befund_id: str
    vorschlag_override: str | None = None


class BefundeAntwort(BaseModel):
    kapitel: int
    erzeugt_am: str
    jahr: str | None
    befunde: list[Befund]
    # SHA-256 des Kapiteltexts, gegen den die start/end-Offsets in `befunde`
    # berechnet wurden - erlaubt es, beim spaeteren Lesen (befunde_lesen())
    # zu erkennen, ob der Kapiteltext seither ueberschrieben wurde und die
    # Offsets damit veraltet sind. None nur bei vor Einfuehrung dieses Felds
    # geschriebenen befunde_*.json-Dateien.
    quelltext_sha256: str | None = None
    # Wird nicht mitgeschrieben, sondern erst beim Lesen (befunde_lesen())
    # anhand von quelltext_sha256 gesetzt.
    veraltet: bool = False


class AutomatikStartAnfrage(BaseModel):
    max_durchlaeufe: int = Field(default=3, ge=1, le=10)
    # True = Button "Fortsetzen": Phase 2 (Pruefen/Korrigieren) steigt beim
    # zuletzt vermerkten Kapitel/Durchlauf wieder ein statt bei Kapitel 1
    # neu zu beginnen - siehe app/api/pipeline.py:_automatik_lauf.
    fortsetzen: bool = False
    # True = Button "Bestätige alles auf dem Weg": der alle
    # AUTOMATIK_CHECKPOINT_INTERVALL Kapitel greifende Reste-Zwischenstopp
    # (siehe app/api/pipeline.py:_automatik_lauf) wird uebersprungen - fuer
    # unbeaufsichtigte Ueber-Nacht-Laeufe, bei denen der Nutzer ohnehin
    # praktisch immer den Pruefer-Vorschlaegen zustimmt und die
    # uebersprungenen Funde erst am naechsten Morgen gesammelt durchsehen
    # will statt zwischendurch geweckt/gefragt zu werden.
    automatisch_bestaetigen: bool = False
    # True = Ablauf "Weitere Kapitel schreiben" (inkrementelles Erweitern einer
    # begonnenen Geschichte): Phase 2 (Pruefen/Korrigieren) laeuft NUR fuer die
    # in diesem Lauf neu geschriebenen Kapitel, die bereits vorher fertigen
    # Kapitel davor bleiben komplett unangetastet (keine erneute Pruefung, keine
    # automatische Korrektur) - siehe app/api/pipeline.py:_automatik_lauf.
    nur_neue_kapitel: bool = False


class AutomatikStatusAntwort(BaseModel):
    laeuft: bool
    gestartet_am: str | None
    phase: str | None
    aktuelles_kapitel: int | None
    gesamt_kapitel: int | None
    aktueller_durchlauf: int | None
    log: list[str]
    protokoll: list[dict]
    stop_angefordert: bool
    abgeschlossen: bool
    fehler: str | None
    # Server-seitig berechnet (app/core/automatik.py:fortsetzbar), damit das
    # Frontend dieselbe Regel nicht duplizieren muss: True, wenn ein Lauf
    # gestartet wurde, der weder laeuft noch sauber abgeschlossen ist.
    fortsetzbar: bool = False
    # Per POST .../automatik/resten-bestaetigen gesetzt - siehe
    # app/core/automatik.py:zustand_zusammenfassen fuer die Wirkung auf den
    # Projektlisten-Badge.
    resten_bestaetigt: bool = False
    # Nur gesetzt, wenn der letzte Lauf nach ausgeschoepften 502/503-Retries
    # (siehe app/api/pipeline.py:_automatik_mit_retry) pausiert wurde -
    # Kapitel/Phase/Durchlauf des zuletzt gescheiterten Schritts plus
    # extrahierter Fehlercode, fuers Frontend (kompakte Fortsetzen-Zeile).
    fehler_schritt: dict | None = None
    # Live-Text des Autors waehrend des Automatikmodus (siehe
    # app/api/pipeline.py:_automatik_on_event), damit das "Autor"-Fenster in
    # SchreibenPage.tsx auch unbeaufsichtigt mitlaeuft, nicht nur beim
    # interaktiven Schreiben ueber die WebSocket-Verbindung. None ausserhalb
    # der Phase "schreiben" bzw. vor dem ersten Fortschritts-Update.
    aktueller_text: str | None = None


class AutomatikAnknuepfpunkt(BaseModel):
    """Der Kontext, an den das naechste zu schreibende Kapitel anknuepft -
    die "Stand nach Kapitel N"-Zusammenfassung des Vorgaengers (siehe
    app/api/pipeline.py:_kapitel_schreiben_kern, Feld "STAND NACH DEM
    VORIGEN KAPITEL"). Nur fuer die Vorschau vor dem inkrementellen
    Erweitern (automatik/fortsetzen-vorschau), damit der Nutzer sieht,
    worauf aufgebaut wird, bevor er den Lauf startet."""
    kapitel: int
    stand_vorhanden: bool
    stand_text: str | None = None
    # True, wenn kapitel_NN.md nach stand_NN.md geaendert wurde - die
    # Zusammenfassung koennte dann veraltet sein. Wird NICHT automatisch neu
    # erzeugt (nur wenn die Datei ganz fehlt), sondern nur angezeigt, damit
    # der Nutzer sie bei Bedarf selbst im Tab "Stand & Export" neu erstellt.
    stand_veraltet: bool = False


class AutomatikFortsetzenVorschau(BaseModel):
    geplant_bis: int | None
    kapitelplan: dict[int, int] = {}
    geschrieben: list[int] = []
    naechstes_kapitel: int | None = None
    zu_schreiben: list[int] = []
    anknuepfpunkt: AutomatikAnknuepfpunkt | None = None


class AutomatikVerlaufEintrag(BaseModel):
    datum: str
    von: str
    bis: str
    dauer_sekunden: int
    status: str
    fehler: str | None = None
    fortgesetzt: bool = False


class RechtschreibWort(BaseModel):
    wort: str
    satz: str | None
    # Zeichen-Offsets der ERSTEN Fundstelle im vollen Kapiteltext (nicht nur
    # im gekuerzten `satz`) - erlaubt dem Frontend, per Klick direkt an die
    # Stelle im editierbaren Kapiteltext zu springen, analog zu Befund.start/
    # end (siehe app/core/fundstellen.py). None nur, falls das Wort trotz
    # hunspell-Fund im Text nicht als eigenes Wort wiedergefunden wird
    # (sollte praktisch nicht vorkommen, da hunspell direkt gegen denselben
    # Text prueft).
    start: int | None = None
    end: int | None = None


class RechtschreibAntwort(BaseModel):
    unbekannte_woerter: list[RechtschreibWort]
    hunspell_verfuegbar: bool


class CoverPromptAntwort(BaseModel):
    prompt: str


class CoverGenerierenAnfrage(BaseModel):
    prompt: str = Field(min_length=1)


class StoryFrageAnfrage(BaseModel):
    frage: str = Field(min_length=1)


class StoryFrageAntwort(BaseModel):
    antwort: str


class HandlungstextAnfrage(BaseModel):
    handlungstext: str = Field(min_length=1)


class AnalysatorEpocheVorschlagAnfrage(BaseModel):
    text: str = Field(min_length=1)


class AnalysatorStartAnfrage(BaseModel):
    titel: str = ""
    epoche: str
    zweite_epoche: str | None = None
    text: str = Field(min_length=1)


class AnalysatorStartAntwort(BaseModel):
    ordner: str


class AnalysatorStatusAntwort(BaseModel):
    laeuft: bool
    phase: str | None
    aktuelles_kapitel: int | None
    gesamt_kapitel: int | None
    log: list[str]
    abgeschlossen: bool
    fehler: str | None


class AnalyseEintrag(BaseModel):
    # Dateiname im "Analyse"-Ordner (siehe app/core/analysator.py:
    # analyse_speichern) - eindeutiger Identifikator fuer Lesen/Loeschen.
    dateiname: str
    titel: str
    erstellt_am: str
    woerter: int


class EinstellungenAntwort(BaseModel):
    projects_dir: str
    ist_standard: bool
    standard_projects_dir: str
    unterordner_je_epoche: bool
    # Link zu einer externen Bildgenerierungs-Weboberflaeche (z.B. Google
    # Gemini) - im Titelbild-Bereich (Stand & Export) als Schnellzugriff
    # verlinkt, editierbar hier fuer den Fall, dass sich der Link mal aendert.
    bildgenerator_url: str
    bildgenerator_url_ist_standard: bool
    # Zeit-Ueberbrueckungs-Overlay "Unnuetzes Wissen" (siehe
    # frontend/src/components/ZeitUeberbrueckungOverlay.tsx): komplett
    # abschaltbar; wenn an, konfigurierbar nach wie vielen Sekunden es
    # waehrend einer KI-Wartezeit erscheint und wie oft es weiterblaettert.
    unnuetzes_wissen_aktiv: bool
    unnuetzes_wissen_start_sekunden: int
    unnuetzes_wissen_wechsel_sekunden: int


class FundusImportAntwort(BaseModel):
    importierte_projekte: int
    gefundene_figuren: int
    uebersprungen: list[str]


class FundusProjektAntwort(BaseModel):
    gefundene_figuren: int
    uebersprungen: bool


class FundusFigurAntwort(BaseModel):
    """Eine Figur fuer den strukturierten Personen-Editor (siehe
    app/core/fundus.py:Figur) - `felder` ist insertion-ordered (Standard-
    felder zuerst, dann eigene Zusatzfelder), 'Geschichten' als normaler
    Schluessel darin."""
    epoche: str
    name: str
    felder: dict[str, str]


class FundusFigurenAntwort(BaseModel):
    figuren: list[FundusFigurAntwort]
    # STANDARD_FELDER + "Geschichten" aus app/core/fundus.py - dem Frontend
    # bekannt gegeben, damit es beim Anlegen einer neuen Figur die
    # Standard-Feldreihenfolge kennt, ohne sie im TS-Code zu duplizieren.
    standard_felder: list[str]


class FundusFigurAnlegenAnfrage(BaseModel):
    epoche: str
    name: str
    felder: dict[str, str] = {}


class FundusFigurAktualisierenAnfrage(BaseModel):
    epoche: str
    # Aktueller Name - identifiziert die zu aendernde Figur (zusammen mit
    # epoche). Bei Umbenennung bitte NICHT hier den neuen Namen eintragen,
    # sondern in neuer_name.
    name: str
    neuer_name: str | None = None
    # Gesetzt = Figur in eine andere Epoche VERSCHIEBEN (Figur existiert
    # danach nur noch dort). Fuer eine Kopie stattdessen
    # FundusFigurKopierenAnfrage/POST /figuren/kopieren verwenden - das
    # laesst das Original unangetastet.
    neue_epoche: str | None = None
    felder: dict[str, str]


class FundusFigurKopierenAnfrage(BaseModel):
    epoche: str
    name: str
    ziel_epoche: str
    # Optional - falls im Ziel schon eine gleichnamige Figur existiert oder
    # die Kopie bewusst einen anderen Namen bekommen soll. Sonst wird der
    # Name der Quelle uebernommen.
    neuer_name: str | None = None


class FundusFeldHinzufuegenAnfrage(BaseModel):
    epoche: str
    name: str
    feld_name: str
    wert: str = ""
    # True: das Feld (leer) auch bei allen anderen Figuren im gesamten
    # Fundus ergaenzen, die es noch nicht haben - False: nur bei dieser
    # einen Figur.
    fuer_alle: bool = False


class ProjektBereinigenAntwort(BaseModel):
    geloeschte_bak: int
    geloeschte_stand: int


class ProjektZuruecksetzenAntwort(BaseModel):
    geloeschte_dateien: int
    geloeschte_bak: int


class ProjektOrdnerUmbenennenAnfrage(BaseModel):
    # Frei gewaehlter Wunschname - wird serverseitig zu einem dateisystem-
    # tauglichen Slug normalisiert (siehe geruest.ordnername_aus_titel).
    name: str = Field(min_length=1)


class ProjektOrdnerUmbenennenAntwort(BaseModel):
    neuer_ordner: str


class EinstellungenAnfrage(BaseModel):
    # Leer/None setzt den Override zurueck auf standard_projects_dir.
    projects_dir: str | None = None
    unterordner_je_epoche: bool = False
    # Leer/None setzt den Override zurueck auf den Standard-Bildgenerator-Link.
    bildgenerator_url: str | None = None
    # PUT /api/einstellungen ist ein vollstaendiger Ersatz, kein Teilupdate
    # (siehe test_einstellungen_api.py) - fehlende Felder fallen auf diese
    # Defaults zurueck (= bisher fest verdrahtete Werte, 20 s / 20 s). Das
    # Frontend schickt bei jedem Speichern konsequent alle Felder mit.
    unnuetzes_wissen_aktiv: bool = True
    unnuetzes_wissen_start_sekunden: int = Field(default=20, ge=0, le=3600)
    unnuetzes_wissen_wechsel_sekunden: int = Field(default=20, ge=3, le=3600)


class WissenEintrag(BaseModel):
    nummer: int
    kategorie: str
    thema: str
    kuriositaet: str
    hintergrund: str
    quelle: str | None = None


class WissenNaechstesAntwort(BaseModel):
    eintrag: WissenEintrag
    # 1-basierte Position innerhalb der aktuell gemischten Runde (siehe
    # app/db.py:wissen_status_*) und deren Gesamtlaenge - fuer eine
    # "X von Y"-Anzeige, die tatsaechlich den Fortschritt durch die
    # gemischte Reihenfolge zeigt statt nur die rohe DB-ID.
    position: int
    gesamt: int


class Benutzer(BaseModel):
    id: int
    username: str
    ist_admin: bool


class LoginEingabe(BaseModel):
    username: str
    password: str


class BenutzerEintrag(BaseModel):
    id: int
    username: str
    ist_admin: bool
    created_at: str


class BenutzerAnlegenAnfrage(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=8)
    ist_admin: bool = False
