$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

$env:PHILO_GEMMA_BASE_URL = "http://127.0.0.1:8794"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  throw "Python was not found in PATH."
}

& $python.Source .\server.py --host 127.0.0.1 --port 18170
