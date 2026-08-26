🇬🇧 [English version](Anleitung.en.md)

# Anleitung: Geschichten Erzähler

Diese Anleitung beschreibt die Bedienung über die **Weboberfläche** (nicht
das CLI-Skript `novelle.py` — falls du das direkt auf der Kommandozeile
nutzt, gilt stattdessen `Bedienungsanleitung.md`).

---

## Merkzettel: der Ablauf in Kurzform

| Schritt | Tab |
|---|---|
| Neue Geschichte anlegen | **Projekte** |
| Gerüst erarbeiten (einmal pro Geschichte) | **Architekt / Gerüst** |
| **— pro Kapitel —** | |
| Kapitel schreiben, automatisch prüfen lassen | **Schreiben** |
| Sichere Prüfer-Korrekturen übernehmen (Anachronismus, Kontinuität, Grammatik) | **Prüfen & Anwenden** |
| Unbekannte Wörter einzeln durchgehen | **Rechtschreibung** |
| Zustand festhalten – immer zuletzt | **Stand & Export** |
| **— am Schluss —** | |
| Alle Kapitel zu einer Datei zusammenfügen, als PDF exportieren, Titelbild erzeugen | **Stand & Export** |

> **Warum „Stand“ erst nach Prüfen?** Der Chronist soll die *endgültige*
> Fassung eines Kapitels zusammenfassen, nicht eine mit noch offenen
> Fehlern. Beim letzten laut Gerüst geplanten Kapitel fügt „Stand erzeugen“
> außerdem automatisch alle Kapitel zu einer Gesamtdatei zusammen.

> **Abkürzung für „Kapitel schreiben“ bis „Sichere Korrekturen
> übernehmen“:** Der **Automatikmodus** (unten im Tab Schreiben) erledigt
> das für alle noch fehlenden Kapitel am Stück, siehe Abschnitt 7 unten.

---

## 1. Die KI-Rollen

Die Geschichte entsteht nicht durch ein einziges Modell, sondern durch
mehrere spezialisierte Rollen, die nacheinander bzw. parallel daran
arbeiten:

| Rolle | Aufgabe | Tab |
|---|---|---|
| **Architekt** | Interviewt dich und erstellt das Story-Gerüst | Architekt / Gerüst |
| **Autor** | Schreibt die eigentlichen Kapitel, ein Kapitel pro Aufruf | Schreiben |
| **Anachronismus-Prüfer** | Historische Fehler gegen Jahr und Verbotsliste | läuft automatisch nach jedem Schreiben, manuell in Prüfen & Anwenden |
| **Kontinuitäts-Prüfer** | Widersprüche zum vorigen Kapitel bzw. zum Nebenstrang, offene Fäden am letzten Kapitel | läuft automatisch nach jedem Schreiben, manuell in Prüfen & Anwenden |
| **Lektor** | Grammatik, Rechtschreibung, Satzbau (u. a. ein dedizierter Prüfer nur für die Verb-Letzt-Stellung in Nebensätzen) | läuft automatisch nach jedem Schreiben, manuell in Prüfen & Anwenden |
| **Chronist** | Fasst nach jedem Kapitel den aktuellen Stand zusammen (Figuren, Beziehungen, offene Fäden) | Stand & Export |
| **Fundus-Pfleger** | Übernimmt Figuren aus abgeschlossenen Geschichten in den wiederverwendbaren Figuren-Fundus | Personen-Fundus |

Alle vier Prüfer-Rollen (Anachronismus, Kontinuität, Lektor, Satzbau) laufen
nach jedem geschriebenen Kapitel automatisch **parallel**, ihre Funde landen
gemeinsam in einer einzigen, farblich nach Kategorie markierten Liste im Tab
**Prüfen & Anwenden**.

Jede Rolle läuft mit eigenem Modell und eigenen Parametern, abgestimmt auf
ihre jeweilige Aufgabe. Der Autor schreibt immer mit Mistral. Welches KI-**Ziel**
(lokal oder per SSH-Tunnel/Netzwerk auf einem anderen Rechner
angesprochen wird, stellst du über die Auswahl oben im Kopfbereich ein —
sie gilt für alle Pipeline-Schritte gleichzeitig und bleibt beim Tab-Wechsel
erhalten.

---

## 2. Eine neue Geschichte anlegen

Im Tab **Projekte**: Titel (optional — ergibt sich oft erst aus dem
Architekten-Interview) und Epoche wählen, dann „Anlegen“. Ohne Titel legt
das Programm einen Platzhalter-Ordner „neu“ an, der automatisch nach dem
im Architekten-Interview gewählten Titel umbenannt wird. Zur Auswahl stehen
die vorbereiteten Epochen (aktuell u. a. Regency, Mittelalter, Altes
Ägypten, Jetzt-2026, Zukunft, Shadowrun) sowie jede selbst über den Tab
**Epoche erstellen** angelegte eigene Epoche.

Direkt danach: Tab **Architekt / Gerüst** öffnen und „Interview neu
führen“. Das Gespräch läuft schrittweise (eine Frage nach der anderen) und
erzeugt am Ende automatisch das Story-Gerüst. **Das Gespräch lässt sich
jederzeit unterbrechen** (Tab schließen, Browser zu) und beim nächsten
Öffnen des Projekts genau an der Stelle fortsetzen, an der es aufgehört
hat — der bisherige Chat-Verlauf wird dafür automatisch zwischengespeichert.
Eine Frage im Interview erlaubt außerdem, bereits im **Personen-Fundus**
gespeicherte Figuren aus früheren, abgeschlossenen Geschichten
wiederzuverwenden, statt jede Figur neu zu erfinden (siehe Abschnitt 8).
Jede eigene Antwort im Chat-Verlauf hat ein kleines ✏️-Symbol daneben —
damit lässt sie sich nachträglich ändern (z. B. wenn du aus Versehen
Enter gedrückt hast oder dir danach noch etwas einfällt); alle seither
gestellten Fragen werden dabei verworfen, der Architekt fragt ab dort neu.

Im erzeugten Gerüst legst du unter anderem fest:

- **Jugendschutz-Stufe** — *Voll*, *Angedeutet* oder *Jugendfrei*. Steuert,
  wie explizit der Autor schreiben darf.
- **Automatische Fortsetzung** — standardmäßig **aus**. Ein zu kurzes
  Kapitel automatisch weiterschreiben zu lassen war wiederholt Ursache für
  doppelte Kapitelüberschriften oder sinnfreien Füll-Text; bei
  ausgeschalteter Fortsetzung bekommst du stattdessen nur einen Hinweis mit
  der aktuellen Wortzahl.
- **Kapitelplan** — Ziel-Ereignis und Zielwortzahl je Kapitel. Das
  **letzte** geplante Kapitel muss laut Architekten-Vorgabe den
  Kernkonflikt (und einen eventuellen Nebenstrang) tatsächlich auflösen,
  kein offenes Ende.

Das Gerüst lässt sich im selben Tab auch von Hand nachbearbeiten — wirkt
sich ab dem nächsten Schreiben-Aufruf aus. **Rahmen** (Zeitangabe, Ort,
Erzählperspektive, Tempus, Tonlage, Jugendschutz-Stufe, Automatische
Fortsetzung), **Titel**, **Unerhörte Begebenheit**, **Figuren** (je eine
Karte mit Name und Details) sowie **Konflikt** und **Nebenstrang** sind
eigene, beschriftete Felder statt eines einzigen Freitext-Blocks —
Nebenstrang ist dabei wirklich optional und bleibt leer, wenn nichts
eingetragen wird. Lässt sich ein Abschnitt nicht sicher in Felder
zerlegen (z. B. ein sehr altes, abweichend formatiertes Gerüst), fällt nur
dieser eine Abschnitt auf einen rohen Markdown-Editor mit Warnhinweis
zurück, ohne dass etwas verloren geht. Ausgangslage vor Kapitel eins/
Offene Punkte/Regeln bleiben Freitext (Monaco-Editor unten). Der
**Kapitelplan** dazwischen ist eine eigene Karte pro Kapitel mit
einzelnen Feldern (Ort, Anwesende Figuren, Ereignis, Zielwortzahl,
Funktion im Spannungsbogen, Stand der Liebeshandlung, Zustand am
Kapitelende) statt einer Freitext-Bulletliste. Zielwortzahl ist ein
Pflicht-Zahlenfeld und bei einem neuen Kapitel schon mit einem Vorschlag
(1500 Wörter, gängiger Richtwert für Kurzgeschichten/Novellen)
vorbefüllt — überschreibbar. Fehlt sie oder ein anderes Feld, markiert
„Speichern“ die betroffene Karte rot, statt den Fehler erst beim
Automatik-Schreiben Tage später bemerken zu lassen. Über „+ Kapitel“/▲▼/
„Löschen“ lassen sich Kapitel ergänzen, verschieben oder entfernen; die
Kapitelnummer ergibt sich automatisch aus der Position. Ein vorhandener
Kapitelplan in einem bisher unbekannten Format wird nie stillschweigend
überschrieben — er bleibt dann als Freitext mit Warnhinweis stehen. Direkt
darunter lassen sich außerdem **Stilproben** hinterlegen: ein bis drei
kurze Textausschnitte, an deren Sprache/Satzrhythmus/Ton sich der Autor
orientieren soll, ohne deren Handlung oder Figuren zu übernehmen.

**Funktion im Spannungsbogen** (Dropdown je Kapitel, nach Freytags
Pyramide) legt fest, welche dramaturgische Aufgabe ein Kapitel in der
Gesamtgeschichte hat — der Autor kennt dieselben sechs Kategorien und
schreibt entsprechend:

- **Exposition** — Einstieg: Figuren, Ort und Ausgangslage werden bekannt
  gemacht, die Spannung ist noch niedrig. Typisch für Kapitel 1.
- **Erregendes Moment** — das Ereignis, das die eigentliche Geschichte
  lostritt. Oft noch Kapitel 1 oder früh in Kapitel 2, direkt nach der
  Exposition.
- **Steigende Handlung** — die Mitte: der Konflikt verschärft sich, es
  gibt Hindernisse, die Einsätze werden höher. Meist der größte Teil der
  mittleren Kapitel.
- **Höhepunkt/Peripetie** — der Wendepunkt: die entscheidende
  Konfrontation, das größte Risiko, die zentrale Entscheidung.
- **Fallende Handlung** — unmittelbar danach: die Folgen des Höhepunkts
  zeigen sich, eventuell noch ein letzter Rückschlag.
- **Auflösung/Lösung** — der Schluss: Konflikt (und ein eventueller
  Nebenstrang) lösen sich endgültig, kein offener Cliffhanger. Das letzte
  Kapitel.

Bei zwei Kapiteln reicht meist Exposition + Erregendes Moment fürs erste,
Höhepunkt + Auflösung fürs zweite. Bei mehr Kapiteln füllt Steigende
Handlung die Mitte. Passt keine der sechs Kategorien exakt, lässt sich
auch ein eigener Freitext eintragen — der Autor orientiert sich dann
sinngemäß an der nächstliegenden Funktion.

---

## 3. Ein Kapitel schreiben (Tab „Schreiben“)

Kapitelnummer eingeben (wird nach jedem erfolgreichen Kapitel automatisch
hochgezählt), optional einen **zusätzlichen Hinweis nur für diesen einen
Versuch** eintragen — nützlich, wenn ein vorheriger Versuch zu weit vom
Gerüst abgewichen ist (z. B. „Maggie muss anwesend sein, das Geheimnis wird
NICHT durch einen Kuss aufgelöst“). Der Hinweis gilt nur für diesen
Durchlauf und wird nirgends dauerhaft gespeichert — für dauerhafte
Änderungen gehört die Korrektur ins Gerüst selbst.

Nach „Schreiben starten“ läuft automatisch mit:

- **Rechtschreibprüfung (hunspell)** gegen ein echtes deutsches
  Wörterbuch (ergänzt die Sprachmodell-Prüfung um erfundene, aber
  grammatisch plausible Wörter)
- **Alle vier Prüfer-Rollen** (Anachronismus, Kontinuität, Lektor,
  Satzbau) direkt im Anschluss, parallel
- **Kapitel-Neustart-**, **Vorzeitiges-Kapitelende-** und
  **Wiederholungs-Erkennung** — schneidet doppelte Kapitelüberschriften,
  verfrüht abgeschlossene, aber weitergeschriebene Szenen sowie intern
  wiederholte Absatzblöcke automatisch ab
- **Stand-Sicherstellung** — fehlt der Stand des vorherigen Kapitels, wird
  er automatisch nachgeholt, bevor das neue Kapitel geschrieben wird

Unterhalb des Kapiteltexts steht außerdem das Feld **„Frage zur
Geschichte“** — beantwortet Verständnisfragen zum bisherigen Verlauf (z. B.
„wie hieß die Nebenfigur aus Kapitel 2 nochmal?“) rein informativ, ohne die
Geschichte fortzuschreiben.

Ein bereits geschriebenes Kapitel wird beim erneuten „Schreiben starten“
überschrieben — die alte Fassung wird automatisch als `.bak`-Datei
gesichert, nichts geht verloren.

---

## 4. Prüfen, anwenden, Rechtschreibung

| Tab | Wirkung |
|---|---|
| **Prüfen & Anwenden** | Zeigt den gesamten, kapitelübergreifenden Kapiteltext in einem Editor mit allen Funden aller vier Prüfer-Rollen (Anachronismus, Stimmigkeit, Kontinuität, Lektorat) daneben, farblich nach Kategorie unterschieden. Jeder Fund mit konkretem, unzweideutigem Ersatzvorschlag lässt sich per Klick (Editor-Widget oder Listen-Button) übernehmen — reiner Text-Ersatz im Browser, kein weiterer KI-Aufruf. „Erneut prüfen“ je Kapitel startet die vier Prüfer-Rollen neu. Über „Ablehnen“ lässt sich ein Fund stattdessen dauerhaft als „kein Fehler“ markieren — z. B. eine in einer FanFic-Epoche bewusst gewählte Kanon-Abweichung (andere Figuren/Orte als im Original). Der Fund verschwindet sofort und wird auch bei einer erneuten Prüfung nicht wieder gemeldet (projektweit, nicht nur für dieses Kapitel). |
| **Rechtschreibung** | Interaktiv: unbekannte Wörter (hunspell) einzeln mit Satzkontext durchgehen — Klick springt an die Stelle im Editor, dort von Hand korrigieren |

Widersprüchliche Vorschläge zweier Prüfer sowie Funde, deren Textstelle
nicht mehr auffindbar ist (weil der Text sich inzwischen geändert hat),
werden **nicht** automatisch übernommen — sie bleiben zur manuellen
Entscheidung sichtbar.

Sobald der Automatikmodus fertig ist und du „Prüfung abschließen“ klickst,
bietet ein Dialog an, das Projekt zu **bereinigen**: löscht alle
`.bak`-Sicherungsdateien sowie alle Zwischenstände bis auf den letzten.
Kapitel, Gerüst, Verbotsliste und Personas bleiben dabei unangetastet. Ein
Haken im selben Dialog (standardmäßig gesetzt, unabhängig vom Bereinigen)
aktualisiert außerdem den **Personen-Fundus** mit den Figuren dieses
Projekts.

---

## 5. Stand festhalten und exportieren

Tab **Stand & Export**:

- **„Stand erzeugen“** — der Chronist fasst den Zustand nach dem
  angegebenen Kapitel zusammen (Figuren, Beziehungen, offene Fäden,
  bereits verwendete Bilder/Formulierungen). Ist es das laut Gerüst
  **letzte** geplante Kapitel, werden automatisch alle Kapitel zu einer
  Gesamtdatei zusammengefügt. Daneben „🔄 Neu laden“ — zeigt nur den
  zuletzt gespeicherten Stand erneut an, ohne den Chronisten (und damit
  einen KI-Aufruf) erneut zu bemühen; nützlich, wenn du seitdem z. B. im
  Tab „Rechtschreibung“ noch etwas am Kapiteltext geändert hast.
- **„Titelbild“** — schlägt (per KI) einen deutschen Bildprompt aus dem
  Gerüst vor, oder eigenen Prompt eintragen, dann generieren lassen.
  Braucht ein KI-Ziel mit hinterlegtem **Bild-Port** (siehe Abschnitt 8) —
  ohne ein solches Ziel bleibt der Bereich ausgeblendet.
- **„Alle Kapitel zusammenfassen“** — dasselbe wie der Auto-Export, manuell
  jederzeit möglich.
- **„Als PDF-Buch herunterladen“** — erzeugt ein gestaltetes PDF im Stil
  eines Taschenbuchs, direkt aus den aktuellen Kapitel-Dateien.
- **„Zwischenstand zusammenfassen“** (von/bis Kapitel) — für einen
  Auszug, ohne die Geschichte fertigstellen zu müssen. Auch hier zeigt
  „🔄 Neu laden“ neben der Vorschau die zuletzt genutzte der beiden
  Zusammenfassungen erneut an.

Die Gesamtdatei sowie benannte Zwischenstände landen im Story-Ordner
selbst, nicht im internen Arbeitsdateien-Unterordner — dort findest du sie
leicht wieder, ohne technische Interna durchsuchen zu müssen.

---

## 6. Personas und Epoche erstellen

Im Tab **Personas** lassen sich die Rollen-Anweisungen (Architekt, Autor,
Anachronismus-Prüfer, Chronist, Kontinuitäts-Prüfer, Lektor, Satzbau-
Prüfer) für das aktuell offene Projekt individuell anpassen — Änderungen
wirken sich nur auf **dieses** Projekt aus, nicht rückwirkend auf andere
oder auf die zentrale Epochen-Bibliothek.

Im Tab **Epoche erstellen** legst du ein komplett neues Setting an (Fragen
zu Name, Zeitraum, Gesellschaftsordnung, der einen Statusregel als
dramaturgisches Spannungsmittel, bei erfundenen Welten auch, von welchem
bekannten Franchise Abstand gehalten werden soll). Das Ergebnis ist ein
**Rohentwurf** — die Verbotsliste und Prüfer-Checkliste sind nur mit „HIER
ERGÄNZEN“ markiert und sollten vor dem produktiven Einsatz noch
recherchiert werden.

---

## 7. Automatikmodus (alle Kapitel am Stück)

Unten im Tab **Schreiben** schreibt der **Automatikmodus** alle laut
Gerüst noch fehlenden Kapitel hintereinander und wendet danach für jedes
Kapitel automatisch alle eindeutigen Prüfer-Korrekturen an (bis zu der
eingestellten Zahl **„Max. Durchläufe je Kapitel“**). Widersprüchliche
Vorschläge, nicht auffindbare Stellen und unbekannte Wörter werden dabei
**nicht** automatisch entschieden — die bleiben wie gewohnt im Tab
**Prüfen & Anwenden** bzw. **Rechtschreibung** zur manuellen Durchsicht
liegen. Der Lauf arbeitet im Hintergrund auf dem Server weiter, auch wenn
du den Tab schließt oder den Browser zumachst.

**Live-Fortschritt:** Das „Autor“-Fenster zeigt den gerade entstehenden
Kapiteltext auch im Automatikmodus live an (nicht nur beim interaktiven
Schreiben), und das Status-Log meldet bei einem langsamen KI-Ziel alle
gut 20 Sekunden eine Zwischenmeldung („… schreibt noch, ca. N Wörter
bisher“), solange eine Antwort noch aussteht — so ist auch bei mehreren
Minuten reiner Schreibzeit erkennbar, dass der Lauf aktiv arbeitet und
nicht hängt.

**Automatische Zwischenstopps:** Alle drei Kapitel hält der Lauf von sich
aus an, falls sich seit Laufbeginn ungelöste Prüfer-Funde angesammelt
haben (Konflikte, nicht mehr auffindbare Stellen, unbekannte Wörter) —
damit sich Probleme nicht unbemerkt über viele weitere Kapitel
fortsetzen, bevor du sie siehst. Ein Blick ins Protokoll bzw. in **Prüfen
& Anwenden**, dann normal mit „Fortsetzen“ weitermachen.

**Bei einem Verbindungsabbruch zum KI-Ziel** (z. B. Ollama kurzzeitig nicht
erreichbar) gibt der Automatikmodus nicht sofort auf: er versucht denselben
Schritt bis zu dreimal erneut, im Abstand von 5 Minuten (also 5, 10 und 15
Minuten nach dem ersten Fehlschlag). Der Lauf gilt währenddessen weiter als
aktiv, der „Stoppen“-Button bleibt wirksam. Erst wenn auch der letzte
Versuch scheitert, pausiert der Lauf.

**Wird der Lauf unterbrochen** (nach ausgeschöpften Wiederholungsversuchen,
durch einen Zwischenstopp, weil du selbst „Stoppen“ geklickt hast, oder
sogar durch einen Neustart des Servers mitten im Lauf), merkt sich das
Programm exakt, an welcher Stelle das passiert ist, und bietet einen
eigenen **„Fortsetzen“**-Button an, der den Lauf exakt dort fortsetzt —
niemals von Kapitel 1 an neu. Der „Stoppen“-Button zeigt nach dem Klick
„Wird gestoppt…“ an: Ein bereits laufender KI-Schritt wird nicht
mittendrin abgebrochen, sondern erst zu Ende geführt, bevor der Lauf
tatsächlich pausiert.

Unter **„Lauf-Historie“** lässt sich außerdem jeder bisherige
Automatik-Lauf dieses Projekts nachschlagen — Datum, Zeitraum, Laufzeit
und ob er sauber abgeschlossen, mit Fehler abgebrochen oder gestoppt
wurde.

---

## 8. Personen-Fundus

Im Tab **Personen-Fundus** liegt eine einzige, konten- statt
projektgebundene Datei mit Figuren aus **abgeschlossenen** Geschichten,
gegliedert nach Epoche. „Importieren“ übernimmt Figuren einer fertigen
Geschichte automatisch in den Fundus; im Architekten-Interview lassen sie
sich danach für eine neue Geschichte derselben Epoche wiederverwenden,
statt jede Figur neu zu erfinden.

---

## 9. KI-Ziele und Einstellungen

Im Tab **KI-Ziele** hinterlegst du, wo Ollama läuft: lokal, direkt per
Netzwerk-Adresse, oder über einen SSH-Tunnel auf einem entfernten Rechner.
Ein Ziel kann als Favorit markiert werden — es wird dann beim nächsten
Start automatisch vorausgewählt. Zusätzlich lässt sich pro Ziel ein
**Bild-Port** hinterlegen, wenn auf demselben Rechner auch ein
Bildgenerierungs-Server läuft — erst dann erscheint der Titelbild-Bereich
im Tab „Stand & Export“ (siehe Abschnitt 5).

Im Tab **Einstellungen** legst du fest, wo neue Geschichten auf der
Festplatte gespeichert werden, und ob dabei automatisch ein Unterordner je
Epoche angelegt wird. Im Tab **Benutzer** verwaltest du (als Admin) die
Konten, mit denen sich Nutzer anmelden — jedes Konto sieht ausschließlich
seine eigenen Projekte. Alle drei Tabs sind nur für Admin-Konten sichtbar.

---

Siehe auch: **Hilfe** (Kopfbereich) für den Ablauf einer komplett neuen
Geschichte Schritt für Schritt sowie den Umgang mit unterbrochenen
Verbindungen.
