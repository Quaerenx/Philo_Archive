param(
    [string]$ModelPath = "C:\Users\PP\Downloads\gemma-4-26B-A4B-it-Q4_K_M.gguf",
    [string]$ReaderHost = "127.0.0.1",
    [int]$ReaderPort = 8793,
    [string]$GemmaHost = "127.0.0.1",
    [int]$GemmaPort = 9999,
    [int]$ContextSize = 8192,
    [string]$GpuLayers = "auto",
    [switch]$StopGemmaWithReader
)

$ErrorActionPreference = "Stop"
$Site = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $Site "data\runtime.local"
$GemmaBaseUrl = "http://${GemmaHost}:${GemmaPort}"
$ReaderBaseUrl = "http://${ReaderHost}:${ReaderPort}"
$RuntimeStatePath = Join-Path $RuntimeDir "gemma-state.json"
$ReaderAlreadyRunning = $false
$StartedReader = $false
$StartedGemma = $false
$ReaderProcess = $null
$GemmaProcess = $null

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

function Repair-DuplicateProcessPath {
    $pathKeys = @(
        [System.Environment]::GetEnvironmentVariables().Keys |
            Where-Object { [string]$_ -ieq "path" }
    )
    if ($pathKeys.Count -gt 1 -and $pathKeys -ccontains "Path" -and $pathKeys -ccontains "PATH") {
        Remove-Item Env:PATH -ErrorAction Stop
    }
}

function Test-PortListening {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Get-LegacyGemmaListenerPorts {
    param([int]$FixedPort)
    return @(
        @(8081, 8794) |
            Where-Object { $_ -ne $FixedPort -and (Test-PortListening -Port $_) }
    )
}

function Test-PortLoopbackOnly {
    param([int]$Port)
    $connections = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
    if (!$connections.Count) {
        return $false
    }
    foreach ($connection in $connections) {
        $address = $null
        if (
            ![System.Net.IPAddress]::TryParse($connection.LocalAddress, [ref]$address) -or
            ![System.Net.IPAddress]::IsLoopback($address)
        ) {
            return $false
        }
    }
    return $true
}

function Test-LoopbackHost {
    param([string]$HostName)
    if (!$HostName) {
        return $false
    }
    if ($HostName -eq "localhost") {
        return $true
    }
    $address = $null
    if (![System.Net.IPAddress]::TryParse($HostName, [ref]$address)) {
        return $false
    }
    return (
        $address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
        [System.Net.IPAddress]::IsLoopback($address)
    )
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
    $lines.Add("This PC: http://${HostName}:${Port}/")
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

function Write-GemmaRuntimeState {
    param(
        [ValidateSet("starting", "ready", "failed", "stopped")]
        [string]$State,
        [string]$Detail = "",
        [int]$RuntimeProcessId = 0
    )
    $payload = [ordered]@{
        schema_version = 1
        state = $State
        base_url = $GemmaBaseUrl
        updated_at = [DateTime]::UtcNow.ToString("o")
        launcher_pid = $PID
        runtime_pid = $RuntimeProcessId
        detail = $Detail
    }
    $temporaryPath = "${RuntimeStatePath}.tmp.${PID}"
    $json = $payload | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText(
        $temporaryPath,
        $json,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Move-Item -LiteralPath $temporaryPath -Destination $RuntimeStatePath -Force
}

function Wait-ReaderReady {
    param(
        [string]$BaseUrl,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 30
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process -and $Process.HasExited) {
            throw "Reader process exited with code $($Process.ExitCode)."
        }
        if (Test-ReaderReady -BaseUrl $BaseUrl) {
            return
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Reader did not become ready at ${BaseUrl} within ${TimeoutSeconds} seconds."
}

function Wait-GemmaReady {
    param(
        [string]$BaseUrl,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 120
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process -and $Process.HasExited) {
            throw "Gemma runtime exited with code $($Process.ExitCode)."
        }
        try {
            Invoke-WebRequest -UseBasicParsing "${BaseUrl}/v1/models" -TimeoutSec 2 | Out-Null
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "Gemma runtime did not become ready at ${BaseUrl} within ${TimeoutSeconds} seconds."
}

function Wait-OwnedProcesses {
    param(
        [System.Diagnostics.Process]$Reader,
        [bool]$OwnsReader,
        [System.Diagnostics.Process]$Gemma,
        [bool]$OwnsGemma
    )
    $gemmaExitReported = $false
    while ($true) {
        if ($OwnsReader -and $Reader -and $Reader.HasExited) {
            throw "Reader process exited with code $($Reader.ExitCode)."
        }
        if ($OwnsGemma -and $Gemma -and $Gemma.HasExited -and !$gemmaExitReported) {
            $gemmaExitReported = $true
            Write-GemmaRuntimeState -State "failed" -Detail "Gemma runtime exited after startup."
            Write-Warning "Gemma runtime exited. Reader browsing, search, and notes remain available."
            if (!$OwnsReader) {
                return
            }
        }
        Start-Sleep -Seconds 1
    }
}

if (!(Test-LoopbackHost -HostName $ReaderHost)) {
    Stop-WithHint "ReaderHost must be loopback-only; unauthenticated LAN exposure is disabled." @(
        "Use the default: .\run_reader_with_gemma.ps1",
        "Or pass -ReaderHost 127.0.0.1 explicitly."
    )
}

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (!$PythonCommand) {
    Stop-WithHint "Python was not found in PATH." @(
        "Install Python or add it to PATH.",
        "Verify with: python --version"
    )
}
Repair-DuplicateProcessPath

if (Test-PortListening -Port $ReaderPort) {
    if (!(Test-PortLoopbackOnly -Port $ReaderPort)) {
        Stop-WithHint "Reader port ${ReaderPort} has a non-loopback listener." @(
            (Get-PortOwnerHint -Port $ReaderPort),
            "Stop the existing LAN-bound reader or service before restarting Philo Archive.",
            "The supported reader boundary is 127.0.0.1 only."
        )
    }
    if (Test-ReaderReady -BaseUrl $ReaderBaseUrl) {
        $ReaderAlreadyRunning = $true
        Write-Host "Philo Archive reader already running at ${ReaderBaseUrl}"
        $readerOwner = Get-PortOwnerHint -Port $ReaderPort
        if ($readerOwner) {
            Write-Host $readerOwner
        }
    } else {
        Stop-WithHint "Reader port ${ReaderPort} is already used by another process." @(
            (Get-PortOwnerHint -Port $ReaderPort),
            "Stop that process and run this script again.",
            "Or start Philo Archive on another port: .\run_reader_with_gemma.ps1 -ReaderPort 8795"
        )
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$env:PHILO_GEMMA_BASE_URL = $GemmaBaseUrl
$env:PHILO_GEMMA_MODEL_NAME = "gemma-4-26B-A4B-it-Q4_K_M"
$env:PHILO_GEMMA_RUNTIME = "llama.cpp b9371-f12cc6d0f"
$env:PHILO_GEMMA_STATE_PATH = $RuntimeStatePath

Write-GemmaRuntimeState -State "starting" -Detail "Gemma startup requested."
$startupClock = [System.Diagnostics.Stopwatch]::StartNew()
$readerStdout = Join-Path $RuntimeDir "reader-server.out.log"
$readerStderr = Join-Path $RuntimeDir "reader-server.err.log"
$gemmaStdout = Join-Path $RuntimeDir "llama-server.out.log"
$gemmaStderr = Join-Path $RuntimeDir "llama-server.err.log"
$gemmaSetupError = ""
$GemmaReady = $false

try {
    if ($ReaderAlreadyRunning) {
        Write-Host "Checking Gemma runtime for the existing reader..."
    } else {
        Write-Host "Starting Philo Archive reader on ${ReaderHost}:${ReaderPort}"
        $readerArgs = @(".\server.py", "--host", $ReaderHost, "--port", [string]$ReaderPort)
        $ReaderProcess = Start-Process `
            -WindowStyle Hidden `
            -PassThru `
            -FilePath $PythonCommand.Source `
            -ArgumentList $readerArgs `
            -WorkingDirectory $Site `
            -RedirectStandardOutput $readerStdout `
            -RedirectStandardError $readerStderr
        $StartedReader = $true
    }
    Write-ReaderOpenUrls -HostName $ReaderHost -Port $ReaderPort

    $legacyGemmaPorts = @(Get-LegacyGemmaListenerPorts -FixedPort $GemmaPort)
    if (Test-PortListening -Port $GemmaPort) {
        Write-Host "Gemma runtime already listening at ${GemmaBaseUrl}"
    } elseif ($legacyGemmaPorts.Count -gt 0) {
        $gemmaSetupError = "Legacy Gemma port(s) $($legacyGemmaPorts -join ', ') are listening. Stop the legacy runtime before starting shared port ${GemmaPort}."
    } elseif (!(Test-Path -LiteralPath $ModelPath)) {
        $gemmaSetupError = "Model file not found: ${ModelPath}"
    } else {
        $llamaServer = Get-Command llama-server.exe -ErrorAction SilentlyContinue
        if (!$llamaServer) {
            $gemmaSetupError = "llama-server.exe was not found in PATH."
        } else {
            $gemmaArgs = @(
                "-m", $ModelPath,
                "--host", $GemmaHost,
                "--port", [string]$GemmaPort,
                "--ctx-size", [string]$ContextSize,
                "--n-gpu-layers", $GpuLayers
            )
            Write-Host "Starting Gemma runtime at ${GemmaBaseUrl}"
            try {
                $GemmaProcess = Start-Process `
                    -WindowStyle Hidden `
                    -PassThru `
                    -FilePath $llamaServer.Source `
                    -ArgumentList $gemmaArgs `
                    -RedirectStandardOutput $gemmaStdout `
                    -RedirectStandardError $gemmaStderr
                $StartedGemma = $true
                Write-GemmaRuntimeState `
                    -State "starting" `
                    -Detail "Gemma process started and is loading the model." `
                    -RuntimeProcessId $GemmaProcess.Id
            } catch {
                $gemmaSetupError = "Could not start llama-server.exe: $($_.Exception.Message)"
            }
        }
    }

    if ($gemmaSetupError) {
        Write-GemmaRuntimeState -State "failed" -Detail $gemmaSetupError
        Write-Warning "${gemmaSetupError} Reader browsing, search, and notes remain available."
    }

    try {
        Wait-ReaderReady -BaseUrl $ReaderBaseUrl -Process $ReaderProcess
    } catch {
        Stop-WithHint $_.Exception.Message @(
            "Check stdout log: ${readerStdout}",
            "Check stderr log: ${readerStderr}",
            (Get-PortOwnerHint -Port $ReaderPort)
        )
    }
    $readerReadySeconds = [Math]::Round($startupClock.Elapsed.TotalSeconds, 2)
    Write-Host "Reader ready in ${readerReadySeconds}s at ${ReaderBaseUrl}"

    if (!$gemmaSetupError) {
        try {
            Wait-GemmaReady -BaseUrl $GemmaBaseUrl -Process $GemmaProcess
            $GemmaReady = $true
            $runtimeProcessId = if ($GemmaProcess) { $GemmaProcess.Id } else { 0 }
            Write-GemmaRuntimeState `
                -State "ready" `
                -Detail "Gemma runtime is ready." `
                -RuntimeProcessId $runtimeProcessId
            $gemmaReadySeconds = [Math]::Round($startupClock.Elapsed.TotalSeconds, 2)
            Write-Host "Gemma runtime ready in ${gemmaReadySeconds}s at ${GemmaBaseUrl}"
        } catch {
            $gemmaSetupError = $_.Exception.Message
            if ($StartedGemma -and $GemmaProcess -and !$GemmaProcess.HasExited) {
                Stop-Process -Id $GemmaProcess.Id -ErrorAction SilentlyContinue
            }
            $StartedGemma = $false
            Write-GemmaRuntimeState -State "failed" -Detail $gemmaSetupError
            Write-Warning "${gemmaSetupError} Reader browsing, search, and notes remain available."
            if (Test-PortListening -Port $GemmaPort) {
                $ownerHint = Get-PortOwnerHint -Port $GemmaPort
                if ($ownerHint) {
                    Write-Warning $ownerHint
                }
            }
        }
    }

    Write-Host "Health check: python .\scripts\check_local_runtime.py --plain"
    if ($GemmaReady) {
        Write-Host "Reader and Gemma runtime are ready."
    } else {
        Write-Host "Reader is ready. Gemma translation is unavailable; see the warning and runtime logs above."
    }

    if ($ReaderAlreadyRunning -and $StartedGemma) {
        Write-Host "Gemma runtime started for the existing reader. Keep this window open while monitoring it."
        Write-Host "Press Ctrl+C to stop monitoring; the shared Gemma runtime remains running by default."
    } elseif ($StartedReader -or $StartedGemma) {
        Write-Host "Keep this window open; press Ctrl+C to stop the Reader."
        Write-Host "The shared Gemma runtime remains running unless -StopGemmaWithReader was specified."
    } else {
        return
    }
    Wait-OwnedProcesses `
        -Reader $ReaderProcess `
        -OwnsReader $StartedReader `
        -Gemma $GemmaProcess `
        -OwnsGemma $StartedGemma
} finally {
    if ($StartedReader -and $ReaderProcess -and !$ReaderProcess.HasExited) {
        Write-Host "Stopping Reader process $($ReaderProcess.Id)"
        Stop-Process -Id $ReaderProcess.Id -ErrorAction SilentlyContinue
    }
    if ($StartedGemma -and $GemmaProcess -and !$GemmaProcess.HasExited) {
        if ($StopGemmaWithReader) {
            Write-Host "Stopping Gemma runtime process $($GemmaProcess.Id)"
            Stop-Process -Id $GemmaProcess.Id -ErrorAction SilentlyContinue
            Write-GemmaRuntimeState -State "stopped" -Detail "Gemma runtime stopped with the launcher."
        } else {
            Write-Host "Leaving shared Gemma runtime process $($GemmaProcess.Id) running at ${GemmaBaseUrl}"
        }
    }
}
