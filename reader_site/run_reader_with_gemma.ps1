param(
    [string]$ModelPath = "C:\Users\PP\Downloads\gemma-4-26B-A4B-it-Q4_K_M.gguf",
    [string]$ReaderHost = "0.0.0.0",
    [int]$ReaderPort = 8793,
    [string]$GemmaHost = "127.0.0.1",
    [int]$GemmaPort = 8794,
    [int]$ContextSize = 8192,
    [string]$GpuLayers = "auto"
)

$ErrorActionPreference = "Stop"
$Site = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $Site "data\runtime.local"
$GemmaBaseUrl = "http://${GemmaHost}:${GemmaPort}"
$StartedGemma = $false
$GemmaProcess = $null

function Test-PortListening {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Wait-GemmaReady {
    param([string]$BaseUrl)
    for ($i = 0; $i -lt 120; $i++) {
        try {
            Invoke-WebRequest -UseBasicParsing "${BaseUrl}/v1/models" -TimeoutSec 2 | Out-Null
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "Gemma runtime did not become ready at ${BaseUrl}"
}

if (!(Test-Path $ModelPath)) {
    throw "Model file not found: ${ModelPath}"
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if (Test-PortListening -Port $GemmaPort) {
    Write-Host "Gemma runtime already listening at ${GemmaBaseUrl}"
} else {
    $llamaServer = Get-Command llama-server.exe -ErrorAction Stop
    $stdout = Join-Path $RuntimeDir "llama-server.out.log"
    $stderr = Join-Path $RuntimeDir "llama-server.err.log"
    $args = @(
        "-m", $ModelPath,
        "--host", $GemmaHost,
        "--port", [string]$GemmaPort,
        "--ctx-size", [string]$ContextSize,
        "--n-gpu-layers", $GpuLayers
    )
    Write-Host "Starting Gemma runtime at ${GemmaBaseUrl}"
    $GemmaProcess = Start-Process -WindowStyle Hidden -PassThru -FilePath $llamaServer.Source -ArgumentList $args -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $StartedGemma = $true
    Wait-GemmaReady -BaseUrl $GemmaBaseUrl
}

$env:PHILO_GEMMA_BASE_URL = $GemmaBaseUrl
$env:PHILO_GEMMA_MODEL_NAME = "gemma-4-26B-A4B-it-Q4_K_M"
$env:PHILO_GEMMA_RUNTIME = "llama.cpp b9371-f12cc6d0f"

try {
    Write-Host "Starting Philo Archive reader at http://${ReaderHost}:${ReaderPort}"
    Push-Location $Site
    python .\server.py --host $ReaderHost --port $ReaderPort
} finally {
    Pop-Location
    if ($StartedGemma -and $GemmaProcess -and !$GemmaProcess.HasExited) {
        Write-Host "Stopping Gemma runtime process $($GemmaProcess.Id)"
        Stop-Process -Id $GemmaProcess.Id
    }
}
