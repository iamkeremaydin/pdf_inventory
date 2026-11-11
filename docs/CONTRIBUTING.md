# Contributing

Issues and pull requests are welcome.

## Run the checks

```bash
python -m compileall -q pdf_inventory.py test_pdf_inventory.py
```

```bash
python -m unittest -v
```

Both run in GitHub Actions for pull requests and pushes to `main`: on Windows with Python 3.10–3.13, plus Windows and Ubuntu jobs with `pypdf` installed. Keep the code working on Python 3.10, with and without `pypdf`, and on non-Windows paths.

## Ground rules

- Never overwrite or lose a file. Filename cleanup previews first, skips collisions and writes a report before renaming.
- Stay portable: everything the app writes goes into `pdf_inventory_data` next to the program.
- No telemetry or network calls.
- No deleting or moving duplicates without an explicit decision (see the backlog in [QUALITY_CYCLE.md](QUALITY_CYCLE.md)).
- Every user-visible string goes into `TRANSLATIONS` in both `en` and `tr`.
- Add a test that fails on the old behavior for every bug fix.

## Releasing

Set `APP_VERSION` in `pdf_inventory.py`, update [RELEASE_NOTES.md](RELEASE_NOTES.md), then push a tag that matches it (version `MVP 1.0.1` → tag `v1.0.1`). The Release workflow builds Windows, macOS (Apple silicon and Intel) and Linux downloads, launches each one with `--smoke-test --require-pdf-library` (the window opens, closes itself and reports the result as the exit code), and only then creates the GitHub release.
