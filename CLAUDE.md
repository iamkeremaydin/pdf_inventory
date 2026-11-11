# CLAUDE.md

A single-file Tkinter desktop app (`pdf_inventory.py`) that scans folders for PDFs, finds duplicates, exports CSV and cleans download-site tags out of filenames. Tests live in `test_pdf_inventory.py`. User-facing behavior is documented in `README.md`.

## Commands

```bash
python -m compileall -q pdf_inventory.py test_pdf_inventory.py
python -m unittest -v
```

Run both before calling a change done. CI (`.github/workflows/tests.yml`) runs them on Windows with Python 3.10–3.13 and on Windows and Ubuntu with `pypdf==6.21.4`, so keep code working on Python 3.10, with and without `pypdf`, and on non-Windows paths.

## Rules that protect users

- **Never overwrite or lose a file.** Filename cleanup must preview first, skip collisions, and append each rename to its report as it happens. If the report cannot be written, rename nothing.
- **Stay portable.** Everything the app writes goes into `pdf_inventory_data` next to the program, resolved through `program_dir()`. Never read or write `%APPDATA%`, `XDG_CONFIG_HOME` or `~/Library`, and add no hidden fallback location.
- **Keep scan results correct.** Do not follow symlinks or junctions; skip OS folder names only directly below a drive root; hard links count as one file.
- **Keep the UI responsive.** The scan pipeline (`discover_pdfs`, `scan_folder`, `bounded_map`, `inspect_pdf`) stays Tk-free and bounded. Worker threads never touch Tk; they send events through the bounded queue.
- **No telemetry or network calls.** Problems go to the local rotating log.
- **No destructive features** (deleting or moving duplicates) without an explicit decision; see the backlog in `QUALITY_CYCLE.md`.

## Conventions

- Every user-visible string goes into `TRANSLATIONS` in both `en` and `tr`. Turkish text follows `../../md files/Türkçe Arayüz ve İşlemsel E-posta Metinleri İçin Yerelleştirme Rehberi (Kasım 2026).md`; read it only when changing Turkish strings.
- A behavior change updates `README.md`. A planned iteration gets an entry in `QUALITY_CYCLE.md` with reason, change, acceptance, verification, rollback and review date.
- Add a test that fails on the old behavior for every bug fix.
- Commit messages: one imperative sentence, no prefix (e.g. "Make the app fully portable").

## Working efficiently in this repo

- `pdf_inventory.py` is about 2,600 lines. Use Grep to find the function you need and read only that range; don't read the whole file.
- For a broad exploration across the file, use a subagent and keep only its summary in the main thread.
- When running tests to find a failure, look at the failing tests only (e.g. filter the output for `FAIL|ERROR`), not the full verbose log.
- Choose the model and effort level at the start of a session. Sonnet suits routine fixes; use Opus for scan-pipeline concurrency or rename-safety changes.
- Skip plan mode when the change fits in one sentence.
- Start a fresh session (`/clear`) for unrelated tasks, and after two failed corrections on the same issue.
- Keep this file under 200 lines. Add a line only if removing it would cause a mistake.
