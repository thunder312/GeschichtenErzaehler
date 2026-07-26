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
| Sichere Anachronismus-Korrekturen übernehmen | **Prüfen & Anwenden** |
| Grammatik/Rechtschreibung glätten | **Lektorieren** |
| Unbekannte Wörter einzeln durchgehen | **Rechtschreibung** |
| Zustand festhalten – immer zuletzt | **Stand & Export** |
| **— am Schluss —** | |
| Alle Kapitel zu einer Datei zusammenfügen oder als PDF exportieren | **Stand & Export** |

> **Warum „Stand“ erst nach Prüfen/Lektorieren?** Der Chronist soll die
> *endgültige* Fassung eines Kapitels zusammenfassen, nicht eine mit noch
> offenen Fehlern. Beim letzten laut Gerüst geplanten Kapitel fügt „Stand
> erzeugen“ außerdem automatisch alle Kapitel zu `gesamt.md` zusammen.

---

## 1. Die fünf KI-Rollen

Die Geschichte entsteht nicht durch ein einziges Modell, sondern durch
mehrere spezialisierte Rollen, die nacheinander daran arbeiten:

| Rolle | Aufgabe | Tab |
|---|---|---|
| **Architekt** | Interviewt dich und erstellt das Story-Gerüst | Architekt / Gerüst |
| **Autor** | Schreibt die eigentlichen Kapitel, ein Kapitel pro Aufruf | Schreiben |
| **Anachronismus-/Kontinuitäts-Prüfer** | Findet historische Fehler bzw. Widersprüche zwischen Kapiteln | läuft automatisch nach jedem Schreiben, manuell in Prüfen & Anwenden |
| **Chronist** | Fasst nach jedem Kapitel den aktuellen Stand zusammen | Stand & Export |
| **Lektor** | Korrigiert Grammatik/Rechtschreibung | Lektorieren |

Jede Rolle läuft mit eigenem Modell und eigenen Parametern, abgestimmt auf
ihre jeweilige Aufgabe. Welches Modell für welches KI-Ziel (lokal oder per
SSH-Tunnel auf einem anderen Rechner) angesprochen wird, stellst du über die
Auswahl oben rechts im Kopfbereich ein — sie gilt für alle Pipeline-Schritte
gleichzeitig und bleibt beim Tab-Wechsel erhalten.

---

## 2. Eine neue Geschichte anlegen

Im Tab **Projekte**: Titel (optional — ergibt sich oft erst aus dem
Architekten-Interview) und Epoche wählen, dann „Anlegen“. Ohne Titel legt
das Programm einen Platzhalter-Ordner „neu“ an, der automatisch nach dem
im Architekten-Interview gewählten Titel umbenannt wird.

Direkt danach: Tab **Architekt / Gerüst** öffnen und „Interview neu
führen“. Das Gespräch läuft schrittweise (eine Frage nach der anderen) und
erzeugt am Ende automatisch das Story-Gerüst. **Das Gespräch lässt sich
jederzeit unterbrechen** (Tab schließen, Browser zu) und beim nächsten
Öffnen des Projekts genau an der Stelle fortsetzen, an der es aufgehört
hat — der bisherige Chat-Verlauf wird dafür automatisch zwischengespeichert.

Im erzeugten Gerüst legst du unter anderem fest:

- **Jugendschutz-Stufe** — *Voll*, *Angedeutet* oder *Jugendfrei*. Steuert,
  wie explizit der Autor schreiben darf.
- **Autor-Modell** — welches der beiden gleichberechtigten Schreib-Modelle
  (Hermes3 oder Qwen3) die Geschichte tatsächlich schreibt.
- **Automatische Fortsetzung** — standardmäßig **aus**. Ein zu kurzes
  Kapitel automatisch weiterschreiben zu lassen war wiederholt Ursache für
  doppelte Kapitelüberschriften oder sinnfreien Füll-Text; bei
  ausgeschalteter Fortsetzung bekommst du stattdessen nur einen Hinweis mit
  der aktuellen Wortzahl.
- **Kapitelplan** — Ziel-Ereignis und Zielwortzahl je Kapitel.

Das Gerüst lässt sich im selben Tab auch von Hand nachbearbeiten — wirkt
sich ab dem nächsten Schreiben-Aufruf aus.

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
- **Anachronismus- und Kontinuitäts-Prüfung** direkt im Anschluss
- **Kapitel-Neustart-** und **Vorzeitiges-Kapitelende-Erkennung** — schneidet
  doppelte Kapitelüberschriften bzw. verfrüht abgeschlossene, aber
  weitergeschriebene Szenen automatisch ab
- **Stand-Sicherstellung** — fehlt der Stand des vorherigen Kapitels, wird
  er automatisch nachgeholt, bevor das neue Kapitel geschrieben wird

Ein bereits geschriebenes Kapitel wird beim erneuten „Schreiben starten“
überschrieben — die alte Fassung wird automatisch als `.bak`-Datei
gesichert, nichts geht verloren.

---

## 4. Prüfen, anwenden, lektorieren, Rechtschreibung

| Tab | Wirkung |
|---|---|
| **Prüfen & Anwenden** | „Prüfen“ lässt die beiden Prüfer erneut laufen; „Sichere Anachronismus-Funde anwenden“ übernimmt nur Funde mit hoher Sicherheit **und** konkretem Ersatzvorschlag automatisch — in einer Merge-Ansicht (alt/korrigiert). Jede vorgeschlagene Korrektur ist **amber** hinterlegt (ganze Absätze/Sätze statt einzelner Wörter, da sich ein Anachronismus selten in einem Wort beheben lässt) |
| **Lektorieren** | Grammatik/Rechtschreibung/Sprachregister korrigieren, ebenfalls über eine Merge-Ansicht — hier in der normalen Diff-Farbe (Grün/Rot), zur klaren Unterscheidung von Anachronismus-Korrekturen |
| **Rechtschreibung** | Interaktiv: unbekannte Wörter (hunspell) einzeln mit Satzkontext durchgehen — leer lassen = behalten, Ersatzwort eintragen = im ganzen Kapitel ersetzen |

In beiden Merge-Ansichten (Prüfen & Anwenden sowie Lektorieren) hat jede
einzelne Änderung am Ende ihrer ersten Zeile ein eigenes ✓/✗-Symbol: **✓**
übernimmt genau diese eine Korrektur, **✗** verwirft sie und stellt an
dieser Stelle die Original-Fassung wieder her — kein Alles-oder-Nichts,
jede Änderung lässt sich einzeln beurteilen. Der rechte Bereich bleibt
außerdem frei editierbar, falls eine Korrektur nur teilweise passt.

Fällt eine korrigierte Fassung deutlich kürzer aus als das Original, wird
sie **nicht** automatisch übernommen, sondern nur zur Ansicht angezeigt
(Kürzungs-Wächter).

---

## 5. Stand festhalten und exportieren

Tab **Stand & Export**:

- **„Stand erzeugen“** — der Chronist fasst den Zustand nach dem
  angegebenen Kapitel zusammen (Figuren, offene Fäden). Ist es das laut
  Gerüst **letzte** geplante Kapitel, werden automatisch alle Kapitel zu
  `gesamt.md` zusammengefügt.
- **„Alle Kapitel zusammenfassen“** — dasselbe manuell, jederzeit möglich.
- **„Als PDF-Buch herunterladen“** — erzeugt ein gestaltetes PDF im Stil
  eines Taschenbuchs, direkt aus den aktuellen Kapitel-Dateien.
- **„Zwischenstand zusammenfassen“** (von/bis Kapitel) — für einen
  Auszug, ohne die Geschichte fertigstellen zu müssen.

`gesamt.md` sowie benannte Zwischenstände landen im Story-Ordner selbst,
nicht im internen Arbeitsdateien-Unterordner — dort findest du sie leicht
wieder, ohne technische Interna durchsuchen zu müssen.

---

## 6. Personas und Epoche erstellen

Im Tab **Personas** lassen sich die Rollen-Anweisungen (Architekt, Autor,
Prüfer, Chronist, Lektor) für das aktuell offene Projekt individuell
anpassen — Änderungen wirken sich nur auf **dieses** Projekt aus, nicht
rückwirkend auf andere.

Im Tab **Epoche erstellen** legst du ein komplett neues Setting an (12
Fragen, kein KI-Aufruf) — Name, Zeitraum, Gesellschaftsordnung, die eine
Statusregel als dramaturgisches Spannungsmittel, bei erfundenen Welten
auch, von welchem bekannten Franchise Abstand gehalten werden soll. Das
Ergebnis ist ein **Rohentwurf** — die Verbotsliste und Prüfer-Checkliste
sind nur mit „HIER ERGÄNZEN“ markiert und sollten vor dem produktiven
Einsatz noch recherchiert werden.

---

## 7. KI-Ziele und Einstellungen

Im Tab **KI-Ziele** hinterlegst du, wo Ollama läuft: lokal, direkt per
Netzwerk-Adresse, oder über einen SSH-Tunnel auf einem entfernten Rechner.
Ein Ziel kann als Favorit markiert werden — es wird dann beim nächsten
Start automatisch vorausgewählt.

Im Tab **Einstellungen** legst du fest, wo neue Geschichten auf der
Festplatte gespeichert werden, und ob dabei automatisch ein Unterordner je
Epoche angelegt wird.

---

Siehe auch: **Hilfe** (Kopfbereich) für den Ablauf einer komplett neuen
Geschichte Schritt für Schritt sowie den Umgang mit unterbrochenen
Verbindungen.
