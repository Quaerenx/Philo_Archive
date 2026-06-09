# Encoding Policy

The repository stores text files as UTF-8.

The four local source-corpus folders use these exact Korean names:

- `니체_원서수집`
- `비트겐슈타인_원서수집`
- `성경_원서수집`
- `키르케고르_원서수집`

If Windows PowerShell 5.1 displays these names as mojibake, read files with explicit UTF-8 decoding:

```powershell
Get-Content -Encoding UTF8 .\.gitignore
Get-Content -Encoding UTF8 .\reader_site\services\search.py
```

PowerShell 7, `rg`, Python, and the reader-site scripts normally read these files correctly as UTF-8.

Run the encoding contract before publishing changes that touch Korean paths, metadata, or documentation:

```powershell
cd .\reader_site
python .\scripts\check_encoding_contracts.py
```

The contract checks that tracked text files decode as UTF-8, known Korean source-root names are present in release-critical files, and common mojibake fragments do not re-enter the tracked reader-site code or documentation.
