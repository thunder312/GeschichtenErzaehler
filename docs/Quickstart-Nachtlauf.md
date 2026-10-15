🇬🇧 [English version](Quickstart-Nachtlauf.en.md)

# Quickstart: Server → PC → über Nacht schreiben → zurück

Ausführlich mit Testszenario und Stolperfallen:
[Anwendungsfall-Nachtlauf-lokal.md](Anwendungsfall-Nachtlauf-lokal.md).

## Einmalig

- [ ] Lokale App starten: `start-dev.ps1` → `http://localhost:5173`
- [ ] **Einstellungen → 🔄 Abgleich mit Server:** Adresse
      `https://geschichten.daniel-ertl.de`, Benutzer, Passwort →
      **Speichern** → **Verbindung testen**
- [ ] **Einstellungen → KI-Ziele:** `PC (lokal)` (`direct`,
      `http://127.0.0.1:11434`) vorhanden und „Verbindung testen" ok

## Jedes Mal

**Am Server**
1. Projekt anlegen (Tab **Projekte**), Epoche wählen.
2. **Architekt / Gerüst:** Interview, Gerüst speichern.

**Am PC**
3. Tab **Projekte → 🔄 Abgleich mit Server** → Projekt (Status „nur auf dem
   Server") → **⬇ Auf den PC** → Status „✓ identisch".
4. Kopfbereich: KI-Ziel **`PC (lokal)`** anklicken, Punkt muss grün sein.
5. Bild-KI-Container stoppen, Ruhezustand von Windows abschalten.
6. Tab **Schreiben → Automatikmodus:** Max. Durchläufe einstellen,
   **⏻ Danach PC herunterfahren** anhaken, starten. Kurz zusehen, bis der
   Autortext live erscheint.
7. Schlafen gehen. Backend-Fenster und Docker/Ollama laufen lassen.

**Am nächsten Morgen**
8. PC an, `start-dev.ps1`. Tab **Schreiben**: alle Kapitel fertig? Sonst
   Funde ansehen → **Fortsetzen**.
9. Tab **Projekte → Abgleich** → Status „⬆ PC ist neuer" → **⬆ Zum Server**.
10. Am **Server:** **Prüfen & Anwenden**, **Rechtschreibung**,
    **Prüfung abschließen** (Haken „Kopie auf dem PC aufräumen"),
    **Stand & Export**.
11. Am PC: **🧹 Lokal entfernen**.

## Goldene Regeln

- Solange das Projekt am PC liegt, **nicht** am Server daran arbeiten.
- „⚠ beide geändert" → nicht blind überschreiben (kein Merge, nur Sicherung).
- Herunterfahren passiert nur nach **erfolgreichem** Ende, nicht nach
  Zwischenstopp oder Fehler.
- Alles geht vom **PC** aus; der Server kann nichts zum PC schieben.
