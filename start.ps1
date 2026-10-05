$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    & '.venv/Scripts/python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
Write-Host 'ResearchDesk: http://127.0.0.1:8765'
& '.venv/Scripts/python.exe' -m uvicorn researchdesk.app:app --host 127.0.0.1 --port 8765
