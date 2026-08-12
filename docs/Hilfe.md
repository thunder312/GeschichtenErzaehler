# Hilfe

## 1. Eine komplett neue Geschichte — Schritt für Schritt

1. **Projekte** → Titel (optional) und Epoche wählen → „Anlegen“.
2. **Architekt / Gerüst** → „Interview neu führen“ → Fragen der Reihe nach
   beantworten. Am Ende steht automatisch das Story-Gerüst, und der
   Projektordner wird nach dem gewählten Titel umbenannt.
3. **Schreiben** → Kapitel 1 schreiben lassen. Läuft automatisch mit:
   Rechtschreibprüfung sowie alle vier Prüfer-Rollen (Anachronismus,
   Kontinuität, Lektor, Satzbau).
4. Bei Bedarf: **Prüfen & Anwenden** — alle Prüfer-Funde in einer Liste,
   farblich nach Kategorie unterschieden, jeder Fund mit konkretem
   Ersatzvorschlag per Klick übernehmbar. **Rechtschreibung** — unbekannte
   Wörter einzeln mit Kontext durchgehen.
5. **Stand & Export** → „Stand erzeugen“ für Kapitel 1 — *immer als
   letzten Schritt für dieses Kapitel*, damit der festgehaltene Zustand
   auch wirklich die endgültige Fassung ist.
6. Zurück zu Schritt 3 für das nächste Kapitel — die Kapitelnummer wird
   nach jedem erfolgreichen Kapitel automatisch hochgezählt.
7. Nach dem letzten laut Gerüst geplanten Kapitel fügt „Stand erzeugen“
   automatisch alles zu einer Datei zusammen. Über **Stand & Export**
   lässt sich die Geschichte zusätzlich als gestaltetes PDF herunterladen
   oder ein Titelbild dazu generieren.

Statt Schritt 3–6 manuell für jedes Kapitel zu wiederholen, erledigt der
**Automatikmodus** (unten im Tab Schreiben) das für alle fehlenden Kapitel
am Stück — siehe Abschnitt 4 unten.

Ausführliche Erklärung jedes Tabs: siehe **Anleitung** (Kopfbereich).

---

## 2. Wenn ein Kapitel nicht zum Gerüst passt

Manchmal erfindet der Autor eine eigene, unpassende Auflösung — meist gut
erkennbar an mehreren, gleichzeitig schweren Widersprüchen im
Kontinuitäts-Befund. In so einem Fall lohnt sich selten das Nachbessern von
Hand: Da das Schreib-Modell keinen festen Zufalls-Seed verwendet, fällt
schon ein einfacher erneuter Versuch im Tab **Schreiben** meist anders aus.
Reicht das nicht, hilft ein **zusätzlicher Hinweis nur für diesen einen
Versuch** (Feld unterhalb der Kapitelnummer), der dem Autor-Prompt
prominent angehängt wird und Vorrang vor widersprüchlichen Gerüst-Details
hat.

Beim **letzten** geplanten Kapitel gilt eine zusätzliche Regel: Es muss den
Kernkonflikt (und einen eventuellen Nebenstrang) tatsächlich auflösen. Ein
per Hinweis erzwungenes Ereignis, das selbst keine echte Auflösung ist
(sondern nur eine neue, unaufgelöste Wendung), wird vom Kontinuitäts-Prüfer
eigens als solches gemeldet.

---

## 3. Asynchronität: worauf du achten solltest

Die KI-Schritte laufen im Hintergrund (Streaming über WebSocket bzw. ein
laufender Server-Request), während du in der Oberfläche weiterklicken
kannst. Das ist praktisch, hat aber ein paar Fallstricke:

**Verbindung bricht während „Schreiben“ ab (Netzwerk weg, Tab
geschlossen, Server neu gestartet):** Der Kapiteltext wird erst
gespeichert, wenn die KI-Antwort **vollständig** angekommen ist — bei
einem Abbruch mittendrin geht der bisherige Text dieses Versuchs verloren,
es wurde aber auch nichts Halbfertiges auf die Platte geschrieben. Einfach
„Schreiben starten“ erneut anklicken. Das **Architekten-Interview**
verhält sich bewusst anders: Es speichert den Gesprächsverlauf nach jedem
Zug automatisch zwischen und lässt sich beim nächsten Öffnen des Projekts
genau an der unterbrochenen Stelle fortsetzen.

**Nicht am selben Kapitel gleichzeitig in mehreren Tabs arbeiten:** Jeder
Tab (Schreiben, Prüfen & Anwenden, Rechtschreibung) bleibt beim Wechseln
aktiv im Hintergrund bestehen. Startest du z. B. „Prüfen“ für Kapitel 3,
während im Schreiben-Tab noch Kapitel 3 geschrieben wird, prüft das System
zwangsläufig noch die **alte** Fassung, weil die neue erst nach Abschluss
gespeichert wird. Am einfachsten: Einen Schritt abwarten (Fußzeile zeigt
„was die KI gerade macht“), bevor der nächste für dasselbe Kapitel
gestartet wird.

**Nicht dasselbe Projekt gleichzeitig in zwei Browser-Fenstern/-Tabs
öffnen:** Es gibt keine Sperre zwischen zwei parallelen Sitzungen — schreibt
z. B. Fenster A gerade Kapitel 3, während Fenster B ebenfalls Kapitel 3
speichert, gewinnt schlicht, wer zuletzt fertig wird. Die automatische
`.bak`-Sicherung jedes überschriebenen Standes ist hier das Sicherheitsnetz,
falls doch mal etwas verloren scheint.

**„Ollama nicht erreichbar“ bzw. „SSH-Verbindung fehlgeschlagen“:** Das
gewählte KI-Ziel (oben im Kopfbereich) läuft gerade nicht oder ist über
das Netzwerk nicht erreichbar. Im Tab **KI-Ziele** die Verbindung testen;
bei einem entfernten Ziel auch prüfen, ob der Ollama-Container auf dem
Zielrechner läuft.

**Browser-Reload während eines laufenden Schreib-/Prüf-Schritts:** Bricht
die laufende Anfrage genauso ab wie ein Verbindungsverlust (siehe oben) —
nichts Halbfertiges bleibt zurück, der Schritt muss nur erneut gestartet
werden.

---

## 4. Automatikmodus: wenn ein Lauf unterbrochen wird oder lange dauert

Der **Automatikmodus** (unten im Tab Schreiben) schreibt alle fehlenden
Kapitel am Stück und wendet danach für jedes Kapitel automatisch alle
eindeutigen Prüfer-Korrekturen an — läuft im Hintergrund auf dem Server,
auch bei geschlossenem Browser.

**„Das dauert schon sehr lange, ist das noch normal?“** Ohne dedizierte
GPU auf dem KI-Ziel kann ein einzelnes Kapitel (Schreiben plus alle vier
Prüfer-Rollen) durchaus mehrere Minuten dauern — das ist kein Hänger.
Woran man den Unterschied erkennt:

- Das **„Autor“-Fenster** im Tab Schreiben zeigt den gerade entstehenden
  Text auch im Automatikmodus live an.
- Das **Status-Log** meldet bei einer laufenden Antwort etwa alle 20
  Sekunden eine Zwischenzeile mit ungefährer Wortzahl und verstrichener
  Zeit.

Kommt über mehrere Minuten wirklich **gar keine** neue Zeile mehr (auch
keine Fortschrittszeile) und ändert sich auch die Wortzahl im Autor-Fenster
nicht mehr, ist tatsächlich etwas hängen geblieben — dann hilft „Stoppen“
und ein Blick in „Lauf-Historie“, ob ein Fehler vermerkt ist.

**Verbindungsabbruch zum KI-Ziel:** Gerade bei einem entfernten KI-Ziel per
SSH-Tunnel (z. B. ein eigener Rechner zuhause) kann die Verbindung
mittendrin abreißen — nachts z. B. durch die tägliche Zwangstrennung
mancher Internet-Anschlüsse. Bei so einem Verbindungsabbruch gibt der Lauf
nicht sofort auf, sondern versucht denselben Schritt bis zu dreimal erneut,
im Abstand von 5 Minuten (5, 10 und 15 Minuten nach dem ersten
Fehlschlag) — der Lauf zählt währenddessen weiter als aktiv. Erst wenn auch
der letzte Versuch scheitert, bricht der Lauf sauber mit einer
Fehlermeldung ab, **nichts geht verloren**: alle bis dahin geschriebenen
Kapitel und bereits angewendeten Korrekturen bleiben erhalten.

**Automatischer Zwischenstopp alle drei Kapitel:** Häufen sich seit
Laufbeginn ungelöste Prüfer-Funde an (Konflikte, nicht mehr auffindbare
Stellen, unbekannte Wörter), hält der Lauf von sich aus an, statt
unbeaufsichtigt weiterzulaufen und das Problem über viele weitere Kapitel
fortzuschleppen. Das ist kein Fehler, sondern Absicht — kurz im Tab
„Prüfen & Anwenden“ durchsehen, dann normal fortsetzen.

**In keinem dieser Fälle erneut „Automatikmodus starten“ klicken** — das
würde die Prüfphase wieder komplett von Kapitel 1 an durchgehen und
bereits erledigte Kapitel unnötig noch einmal prüfen. Stattdessen
erscheint anstelle dessen (bzw. zusätzlich dazu) ein **„Fortsetzen“**-
Button, direkt daneben steht, wo genau der Lauf aufgehört hat (Fehlercode,
Kapitel, Phase, Durchlauf). Ein Klick darauf setzt exakt dort fort. Dasselbe
gilt, wenn du selbst über „Stoppen“ mittendrin abgebrochen hast — der
Button zeigt danach „Wird gestoppt…“, weil ein bereits laufender KI-Schritt
nicht mittendrin abgewürgt, sondern erst zu Ende geführt wird. Selbst nach
einem Server-Neustart mitten in einem Lauf (z. B. durch ein Update)
bereinigt sich der Zustand beim nächsten Start des Programms von selbst und
bietet „Fortsetzen“ an, statt dauerhaft als „läuft“ hängen zu bleiben.

Über **„Lauf-Historie“** im selben Bereich lassen sich alle bisherigen
Automatik-Läufe dieses Projekts nachschlagen (Datum, Zeitraum, Laufzeit,
Status) — praktisch, um am nächsten Morgen nachzuvollziehen, wie lange ein
über Nacht laufender Durchgang gebraucht hat und ob er sauber durchlief.

---

## 5. Titelbild generieren

Im Tab **Stand & Export** lässt sich zu jeder Geschichte ein Titelbild
erzeugen — vorausgesetzt, unter **KI-Ziele** ist bei mindestens einem Ziel
ein **Bild-Port** hinterlegt (ein separat laufender Bildgenerierungs-
Server auf demselben Rechner). Ohne ein solches Ziel bleibt der Bereich im
Tab ausgeblendet.

„Prompt vorschlagen“ lässt eine KI aus dem Gerüst (Titel, Setting, Figuren,
Konflikt) einen kurzen, deutschen Bildprompt formulieren — bewusst ohne
Eigennamen und ohne Bildtext, da das Bildmodell damit nichts anfangen kann.
Der Prompt bleibt frei editierbar und wird erst unmittelbar vor der
eigentlichen Generierung automatisch ins Englische übersetzt.

