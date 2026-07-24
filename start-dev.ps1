# Startet Backend (uvicorn, Port 8000) und Frontend (vite, Port 5173) fuer
# die lokale Entwicklung, jeweils in einem eigenen Fenster, damit die Logs
# getrennt bleiben und jeder Prozess einzeln per Strg+C beendet werden kann.
$root = $PSScriptRoot

Start-Process pwsh -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"
)

Start-Process pwsh -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\frontend'; npm run dev"
)

Write-Host "Backend startet auf http://localhost:8000, Frontend auf http://localhost:5173"
