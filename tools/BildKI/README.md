# BildKI – Bilder aus deutschen Prompts (Windows, C#/WPF)

Kleines Begleitwerkzeug zum GeschichtenErzähler: ein deutscher Bildprompt wird per
lokalem Ollama ins Englische übersetzt und an **sd-server** (stable-diffusion.cpp,
FLUX.1-schnell) auf Athene geschickt. Das fertige Bild wird angezeigt und gespeichert.

Die Anbindung ist 1:1 aus dem GeschichtenErzähler übernommen
(`backend/app/core/bild_generierung.py`, Übersetzungs-Prompt aus `geruest.py`):

- `POST {sd-server}/sdcpp/v1/img_gen` → Job-ID, danach Polling auf
  `GET /sdcpp/v1/jobs/{id}` bis `status == completed`, PNG aus `result.images[0].b64_json`
- Übersetzung: `POST {ollama}/api/chat`, Modell `gemma4`, `think: false`, Temperatur 0.3
- Defaults: 1024×1024, 4 Schritte, Zeitlimit 600 s, fester Negativ-Prompt

## Voraussetzungen

- Windows 10/11
- .NET 8 SDK (`winget install Microsoft.DotNet.SDK.8`) – nur zum Bauen
- Athene erreichbar: sd-server auf Port 7860, Ollama auf Port 11434
  (die Adressen sind in der App unter „Einstellungen“ änderbar)

## Bauen & Starten

```powershell
cd BildKI
dotnet run
```

Einzelne EXE ohne installierte Runtime (landet in `bin\Release\net8.0-windows\win-x64\publish\BildKI.exe`):

```powershell
dotnet publish -c Release -r win-x64 -p:PublishSingleFile=true -p:SelfContained=true
```

## Bedienung

1. Deutsche Bildbeschreibung eingeben (stichwortartig, kommagetrennt).
   Optional „Hochformat, “ per Häkchen voranstellen.
2. **Übersetzen & Bild erzeugen** – übersetzt (falls das englische Feld leer ist oder der
   deutsche Text sich geändert hat) und startet den Bild-Job.
   Alternativ **Nur übersetzen**, den englischen Prompt kontrollieren/korrigieren und dann erzeugen.
3. Das Bild erscheint rechts. Bei „automatisch speichern“ (Standard) liegt es sofort im
   Speicherordner (Standard: `Bilder\BildKI`) als `JJJJMMTT_HHMMSS_<Prompt-Kürzel>.png`,
   dazu eine gleichnamige `.txt` mit deutschem und englischem Prompt.
   Sonst: **Speichern unter…** – oder **In Zwischenablage**.

Die Einstellungen werden in `%APPDATA%\BildKI\einstellungen.json` abgelegt.

## Dateien

| Datei | Zweck |
|---|---|
| `BildKI.csproj` | Projekt (net8.0-windows, WPF) |
| `App.xaml(.cs)` | Anwendungsstart, gemeinsame Styles |
| `MainWindow.xaml(.cs)` | Oberfläche und Ablauf |
| `Einstellungen.cs` | Persistente Einstellungen (JSON) |
| `Services/OllamaUebersetzer.cs` | Deutsch → Englisch über Ollama |
| `Services/SdServerClient.cs` | Bild-Job auf sd-server starten und abholen |
