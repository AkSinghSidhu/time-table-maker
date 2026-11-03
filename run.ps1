$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & (Join-Path $PSScriptRoot 'setup.ps1')
    }
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -X utf8 main.py @args
    if ($LASTEXITCODE -ne 0) { throw "Application exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
