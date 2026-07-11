param(
    [string]$ModelPath = "C:\Users\PP\Downloads\gemma-4-26B-A4B-it-Q4_K_M.gguf",
    [string]$ReaderHost = "127.0.0.1",
    [int]$ReaderPort = 18170,
    [string]$GemmaHost = "127.0.0.1",
    [int]$GemmaPort = 8794,
    [int]$ContextSize = 8192,
    [string]$GpuLayers = "auto"
)

$ErrorActionPreference = "Stop"
$Site = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $Site "data\runtime.local"
$GemmaBaseUrl = "http://${GemmaHost}:${GemmaPort}"
$ReaderBaseUrl = if ($ReaderHost -eq "0.0.0.0") { "http://127.0.0.1:${ReaderPort}" } else { "http://${ReaderHost}:${ReaderPort}" }
$ReaderAlreadyRunning = $false
$StartedGemma = $false
$GemmaProcess = $null
$PushedSiteLocation = $false

function Stop-WithHint {
    param(
        [string]$Message,
        [string[]]$Hints = @()
    )
    $lines = @(
        "",
        "Philo Archive startup check failed:",
        "  ${Message}"
    )
    if ($Hints.Count) {
        $lines += ""
        $lines += "What to do:"
        foreach ($hint in $Hints) {
            if ($hint) {
                $lines += "  - ${hint}"
            }
        }
    }
    throw ($lines -join [Environment]::NewLine)
}

function Test-PortListening {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Get-PortOwnerHint {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$connection) {
        return ""
    }
    $processId = $connection.OwningProcess
    try {
        $process = Get-Process -Id $processId -ErrorAction Stop
        return "Port ${Port} is used by PID ${processId} ($($process.ProcessName))."
    } catch {
        return "Port ${Port} is used by PID ${processId}."
    }
}

function Get-ReaderOpenUrlLines {
    param(
        [string]$HostName,
        [int]$Port
    )
    $lines = New-Object System.Collections.Generic.List[string]
    if ($HostName -eq "0.0.0.0" -or !$HostName) {
        $lines.Add("This PC: http://127.0.0.1:${Port}/")
        try {
            $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.IPAddress -and
                    $_.IPAddress -notmatch "^127\." -and
                    $_.IPAddress -notmatch "^169\.254\."
                } |
                Select-Object -ExpandProperty IPAddress -Unique
            foreach ($address in $addresses) {
                $lines.Add("Same LAN: http://${address}:${Port}/")
            }
        } catch {
            return $lines
        }
        return $lines
    }
    $lines.Add("Open: http://${HostName}:${Port}/")
    return $lines
}

function Write-ReaderOpenUrls {
    param(
        [string]$HostName,
        [int]$Port
    )
    Write-Host "Open Philo Archive:"
    foreach ($line in Get-ReaderOpenUrlLines -HostName $HostName -Port $Port) {
        Write-Host "  ${line}"
    }
}

function Test-ReaderReady {
    param([string]$BaseUrl)
    try {
        $response = Invoke-WebRequest -UseBasicParsing "${BaseUrl}/api/health" -TimeoutSec 2
        if ($response.StatusCode -ne 200) {
            return $false
        }
        $payload = $response.Content | ConvertFrom-Json -ErrorAction Stop
        return [bool]($payload.status -or $payload.site_root -or $payload.corpora)
    } catch {
        return $false
    }
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

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Stop-WithHint "Python was not found in PATH." @(
        "Install Python or add it to PATH.",
        "Verify with: python --version"
    )
}

if (Test-PortListening -Port $ReaderPort) {
    if (Test-ReaderReady -BaseUrl $ReaderBaseUrl) {
        $ReaderAlreadyRunning = $true
        Write-Host "Philo Archive reader already running at ${ReaderBaseUrl}"
        $readerOwner = Get-PortOwnerHint -Port $ReaderPort
        if ($readerOwner) {
            Write-Host $readerOwner
        }
        Write-Host "Checking Gemma runtime for the existing reader..."
    } else {
        Stop-WithHint "Reader port ${ReaderPort} is already used by another process." @(
            (Get-PortOwnerHint -Port $ReaderPort),
            "Stop that process and run this script again.",
            "Or start Philo Archive on another port: .\run_reader_with_gemma.ps1 -ReaderPort 8795"
        )
    }
}

if (!(Test-Path -LiteralPath $ModelPath)) {
    Stop-WithHint "Model file not found: ${ModelPath}" @(
        "Check that the GGUF model exists at the path above.",
        "Or pass a model explicitly: .\run_reader_with_gemma.ps1 -ModelPath ""D:\models\gemma.gguf"""
    )
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if (Test-PortListening -Port $GemmaPort) {
    Write-Host "Gemma runtime already listening at ${GemmaBaseUrl}"
    try {
        Wait-GemmaReady -BaseUrl $GemmaBaseUrl
    } catch {
        Stop-WithHint "A process is listening on Gemma port ${GemmaPort}, but it did not respond like llama.cpp server." @(
            (Get-PortOwnerHint -Port $GemmaPort),
            "If this is a stale process, stop it and run this script again.",
            "If you intentionally use another Gemma port: .\run_reader_with_gemma.ps1 -GemmaPort 8795"
        )
    }
} else {
    $llamaServer = Get-Command llama-server.exe -ErrorAction SilentlyContinue
    if (!$llamaServer) {
        Stop-WithHint "llama-server.exe was not found in PATH." @(
            "Install or build llama.cpp for Windows.",
            "Add the folder containing llama-server.exe to PATH.",
            "Verify with: Get-Command llama-server.exe"
        )
    }
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
    try {
        Wait-GemmaReady -BaseUrl $GemmaBaseUrl
    } catch {
        if ($StartedGemma -and $GemmaProcess -and !$GemmaProcess.HasExited) {
            Stop-Process -Id $GemmaProcess.Id
        }
        Stop-WithHint "Gemma runtime did not become ready at ${GemmaBaseUrl}." @(
            "Check stdout log: ${stdout}",
            "Check stderr log: ${stderr}",
            "Try a smaller context size: .\run_reader_with_gemma.ps1 -ContextSize 4096"
        )
    }
}

$env:PHILO_GEMMA_BASE_URL = $GemmaBaseUrl
$env:PHILO_GEMMA_MODEL_NAME = "gemma-4-26B-A4B-it-Q4_K_M"
$env:PHILO_GEMMA_RUNTIME = "llama.cpp b9371-f12cc6d0f"

try {
    Push-Location $Site
    $PushedSiteLocation = $true
    if ($ReaderAlreadyRunning) {
        Write-ReaderOpenUrls -HostName $ReaderHost -Port $ReaderPort
        Write-Host "Health check: python .\scripts\check_local_runtime.py --plain"
        if ($StartedGemma) {
            Write-Host "Gemma runtime started for the existing reader. Keep this window open; press Ctrl+C to stop it."
            while ($true) {
                Start-Sleep -Seconds 3600
            }
        }
        Write-Host "Reader and Gemma runtime are ready."
        return
    }

    Write-Host "Starting Philo Archive reader on ${ReaderHost}:${ReaderPort}"
    Write-ReaderOpenUrls -HostName $ReaderHost -Port $ReaderPort
    Write-Host "Health check: python .\scripts\check_local_runtime.py --plain"
    python .\server.py --host $ReaderHost --port $ReaderPort
} finally {
    if ($PushedSiteLocation) {
        Pop-Location
    }
    if ($StartedGemma -and $GemmaProcess -and !$GemmaProcess.HasExited) {
        Write-Host "Stopping Gemma runtime process $($GemmaProcess.Id)"
        Stop-Process -Id $GemmaProcess.Id
    }
}
