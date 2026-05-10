# --- Script d'arrencada per a Windows (PowerShell) ---

Write-Host "🚀 Arrencant el projecte Customer Twin a Windows..." -ForegroundColor Cyan

# 1. Backend
Write-Host "📡 Engegant el Backend (FastAPI) al port 8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000" -NoNewWindow

# 2. Frontend
Write-Host "💻 Engegant el Frontend (Vite) al port 5173..." -ForegroundColor Green
Set-Location frontend
Start-Process powershell -ArgumentList "npm run dev" -NoNewWindow

Write-Host ""
Write-Host "✅ Tot en marxa!" -ForegroundColor Green
Write-Host "🔗 Dashboard: http://127.0.0.1:5173"
Write-Host "⚠️  Per aturar-ho, tanca aquesta finestra o prem CTRL+C (hauràs de tancar els processos de python i node a mà)."
