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

What starts:

- Reader site: `0.0.0.0:8793`, also reachable as `http://127.0.0.1:8793/` on the same machine.
- Local AI sidecar: `127.0.0.1:8794`.
- Runtime logs: `reader_site\data\runtime.local\`.

The local AI sidecar is intentionally local-only. LAN users may open the reader by machine IP, but they do not get direct access to the llama.cpp sidecar.

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

Expected healthy output:

```text
Reader: OK (http://127.0.0.1:8793)
Local AI: OK (http://127.0.0.1:8794)
Local AI models: 1
```

If `Reader` is not ready, start `run_reader_with_gemma.ps1` again. If `Local AI` is not ready, sentence clicks can still select text, but translation/commentary will show an offline state until the sidecar is started.

## Startup Failures

`run_reader_with_gemma.ps1` checks common startup problems before it starts the reader:

- Missing Python: install Python or add it to `PATH`.
- Reader port `8793` already has Philo Archive running: open the existing reader.
- Reader port `8793` is used by another app: stop that app or run with `-ReaderPort 8795`.
- Missing GGUF model: pass the correct model path with `-ModelPath`.
- Missing `llama-server.exe`: add the llama.cpp folder to `PATH`.
- Gemma port `8794` already in use by a different process: stop that process or run with `-GemmaPort 8795`.
- Local AI does not become ready: check `data\runtime.local\llama-server.*.log` or try `-ContextSize 4096`.

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

Details: `local_windows_autostart.md`.
