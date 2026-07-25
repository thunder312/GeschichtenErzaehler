# Hilfe

## 1. Eine komplett neue Geschichte — Schritt für Schritt

1. **Projekte** → Titel (optional) und Epoche wählen → „Anlegen“.
2. **Architekt / Gerüst** → „Interview neu führen“ → Fragen der Reihe nach
   beantworten. Am Ende steht automatisch das Story-Gerüst, und der
   Projektordner wird nach dem gewählten Titel umbenannt.
3. **Schreiben** → Kapitel 1 schreiben lassen. Läuft automatisch mit:
   Rechtschreibprüfung, Anachronismus-/Kontinuitäts-Prüfung.
4. Bei Bedarf: **Prüfen & Anwenden** (sichere Korrekturen übernehmen),
   **Lektorieren** (Grammatik glätten), **Rechtschreibung** (unbekannte
   Wörter durchgehen).
5. **Stand & Export** → „Stand erzeugen“ für Kapitel 1 — *immer als
   letzten Schritt für dieses Kapitel*, damit der festgehaltene Zustand
   auch wirklich die endgültige Fassung ist.
6. Zurück zu Schritt 3 für das nächste Kapitel — die Kapitelnummer wird
   nach jedem erfolgreichen Kapitel automatisch hochgezählt.
7. Nach dem letzten laut Gerüst geplanten Kapitel fügt „Stand erzeugen“
   automatisch alles zu einer Datei zusammen. Über **Stand & Export**
   lässt sich die Geschichte zusätzlich als gestaltetes PDF herunterladen.

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
Tab (Schreiben, Prüfen & Anwenden, Lektorieren, Rechtschreibung) bleibt
beim Wechseln aktiv im Hintergrund bestehen. Startest du z. B. „Prüfen“ für
Kapitel 3, während im Schreiben-Tab noch Kapitel 3 geschrieben wird, prüft
das System zwangsläufig noch die **alte** Fassung, weil die neue erst nach
Abschluss gespeichert wird. Am einfachsten: Einen Schritt abwarten
(Fußzeile zeigt „was die KI gerade macht“), bevor der nächste für dasselbe
Kapitel gestartet wird.

**Nicht dasselbe Projekt gleichzeitig in zwei Browser-Fenstern/-Tabs
öffnen:** Es gibt keine Sperre zwischen zwei parallelen Sitzungen — schreibt
z. B. Fenster A gerade Kapitel 3, während Fenster B ebenfalls Kapitel 3
speichert, gewinnt schlicht, wer zuletzt fertig wird. Die automatische
`.bak`-Sicherung jedes überschriebenen Standes ist hier das Sicherheitsnetz,
falls doch mal etwas verloren scheint.

**„Ollama nicht erreichbar“ bzw. „SSH-Verbindung fehlgeschlagen“:** Das
gewählte KI-Ziel (oben rechts im Kopfbereich) läuft gerade nicht oder ist
über das Netzwerk nicht erreichbar. Im Tab **KI-Ziele** die Verbindung
testen; bei einem entfernten Ziel auch prüfen, ob der Ollama-Container auf
dem Zielrechner läuft.

**Browser-Reload während eines laufenden Schreib-/Prüf-Schritts:** Bricht
die laufende Anfrage genauso ab wie ein Verbindungsverlust (siehe oben) —
nichts Halbfertiges bleibt zurück, der Schritt muss nur erneut gestartet
werden.
