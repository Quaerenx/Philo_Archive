# Local Operator Quickstart

This is the short daily runbook for using the Personal Archive of Literature on a local Windows machine.

## Daily Start

From the repository root:

```powershell
cd .\reader_site
.\run_reader_with_gemma.ps1
```

Open:

```text
http://127.0.0.1:8793/
```

The start script also prints browser-ready links:

```text
Open Philo Archive:
  This PC: http://127.0.0.1:8793/
```

What starts:

- Reader site: `127.0.0.1:8793`, reachable only from the same machine.
- Shared Local AI runtime: `127.0.0.1:9999`.
- Runtime logs: `reader_site\data\runtime.local\`.

The launcher starts the Reader and ensures the shared Local AI runtime is available in parallel. Open the Reader as soon as it prints `Reader ready`; the work-page status changes from `번역기 시작 중` to `번역기 준비됨` without a browser refresh. Reading, search, and notes remain available while the model loads. The shared runtime remains running when the Reader stops unless `-StopGemmaWithReader` is explicitly supplied.

The Reader and shared Local AI runtime are intentionally loopback-only. The reader APIs can read source material and modify personal notes, so unauthenticated LAN binding is rejected. Remote-device access requires a future authenticated deployment layer rather than `-ReaderHost 0.0.0.0`.

## Reader Only

Use this when you only need browsing, search, notes, and study packs without sentence translation:

```powershell
cd .\reader_site
python .\server.py --port 8793
```

## Quick Health Check

With the reader running:

```powershell
cd .\reader_site
python .\scripts\check_local_runtime.py --plain
```

For direct HTTP checks, `/api/health` reports the full redacted Reader readiness summary and `/api/health/gemma` returns only the translation-sidecar state used by the work page. The latter is intentionally cheaper and reflects unavailable/failed states within its shorter failure TTL.

Expected healthy output:

```text
Reader: OK (http://127.0.0.1:8793)
Local AI: OK (http://127.0.0.1:9999)
Local AI models: 1
```

If `Reader` is not ready, start `run_reader_with_gemma.ps1` again. If `Reader` is already running but `Local AI` is not ready, running `run_reader_with_gemma.ps1` again reuses the existing reader and starts/checks the local AI sidecar. If the script starts the sidecar for an existing reader, keep that PowerShell window open.

## Startup Failures

`run_reader_with_gemma.ps1` checks Reader-blocking problems before startup and reports Local AI failures separately:

- Missing Python: install Python or add it to `PATH`.
- Reader port `8793` already has Philo Archive running: the script reuses the existing reader and still checks/starts Local AI.
- Reader port `8793` is used by another app: stop that app or run with `-ReaderPort 8795`.
- Missing GGUF model: the Reader stays available; pass the correct model path with `-ModelPath` and start the launcher again.
- Missing `llama-server.exe`: the Reader stays available; add the llama.cpp folder to `PATH` and start the launcher again.
- Shared Gemma port `9999` already in use by a different process: the Reader stays available; stop the conflicting process. Do not fall back to legacy port `8794`.
- Local AI does not become ready: the Reader stays available; check `data\runtime.local\llama-server.*.log` or try `-ContextSize 4096`.

## Study Workflow

1. Open `Archive` or `Search`.
2. Open a work page.
3. Read the source text.
4. Click a sentence to generate translation and commentary.
5. Mark useful translations as saved.
6. Add notes from the study panel when needed.
7. Review notes in `Notes`.
8. Use `Translations` for generated translations that still need checking.
9. Use `Study` as the saved study pack.

Daily reading loop:

- Click a sentence in the original text.
- Read the translation and commentary in the study panel.
- Use `Next sentence` to keep reading.
- Use `Add note` when the sentence needs a personal note.
- Use `Save` when the translation is worth keeping.
- Use `Translations` -> `Review (n)` later to check saved local AI outputs in one queue.

## If Something Looks Stale

Use a hard browser refresh first. The site uses cache keys on CSS and JavaScript, but a stale browser tab can still keep old assets alive.

Then run:

```powershell
cd .\reader_site
python .\scripts\check_static_routes.py
python .\scripts\check_visual_smoke.py --html-only
```

## Autostart

To start the reader and local AI at Windows logon:

```powershell
.\reader_site\scripts\register_windows_autostart.ps1
```

To remove it:

```powershell
.\reader_site\scripts\unregister_windows_autostart.ps1
```

Details: `docs/local_windows_autostart.md`.
