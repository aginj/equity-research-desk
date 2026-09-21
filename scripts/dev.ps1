#Requires -Version 5.1
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root ".env"))) {
  Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
}
Write-Host "Start the API in one terminal:" -ForegroundColor Yellow
Write-Host "  cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8810"
Write-Host "Start the desk in another:" -ForegroundColor Yellow
Write-Host "  cd frontend; npm run dev"
