# Local Windows Autostart

This project runs the reader and local Gemma runtime through a user-logon Scheduled Task, not a system service.

## Current Recommended Shape

- Task name: `PhiloArchiveReaderGemma`
- Trigger: current user logon
- Action: `powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "<reader_site>\run_reader_with_gemma.ps1"`
- Working directory: `<reader_site>`
- Run level: limited user privileges
- Reader port: `8793`
- Gemma sidecar: `127.0.0.1:8794`
- Runtime logs: `reader_site\data\runtime.local\`

The task intentionally avoids `ExecutionPolicy Bypass` and administrator run level. The llama.cpp sidecar remains bound to `127.0.0.1` even when the reader is exposed on the LAN.

## Register

From the repository root:

```powershell
.\reader_site\scripts\register_windows_autostart.ps1
```

## Unregister

```powershell
.\reader_site\scripts\unregister_windows_autostart.ps1
```

## Manual Start

```powershell
cd .\reader_site
.\run_reader_with_gemma.ps1
```

## Health Checks

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8793/api/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8794/v1/models
```

`/api/health` includes a `gemma` object with `reachable`, `model_count`, and `models`.
