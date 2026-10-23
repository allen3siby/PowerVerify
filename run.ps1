# PowerVerify Startup Script for Windows PowerShell
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Starting PowerVerify..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Virtual environment not found at $py!" -ForegroundColor Red
    Write-Host "Please create it using: uv venv .venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "1. Launching FastAPI Backend on http://127.0.0.1:8000..." -ForegroundColor Green
$backendProc = Start-Process -FilePath $py -ArgumentList "-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $root -PassThru

Start-Sleep -Seconds 2

Write-Host "2. Launching Vite Frontend on http://127.0.0.1:5173..." -ForegroundColor Green
$frontendDir = Join-Path $root "frontend"
$frontendProc = Start-Process -FilePath "npm" -ArgumentList "run dev -- --host 127.0.0.1 --port 5173" -WorkingDirectory $frontendDir -PassThru

Write-Host ""
Write-Host "PowerVerify is running!" -ForegroundColor Cyan
Write-Host "Frontend:  http://127.0.0.1:5173" -ForegroundColor White
Write-Host "Backend:   http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C or close the terminal window to stop." -ForegroundColor Yellow

try {
    Wait-Process -Id $backendProc.Id, $frontendProc.Id
} finally {
    Stop-Process -Id $backendProc.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $frontendProc.Id -ErrorAction SilentlyContinue
}
