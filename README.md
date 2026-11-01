# PDF Master Suite — Inventory

A cross-platform desktop app for scanning folders of PDF files. It shows page counts, sizes and modified dates, finds duplicate files, lets you filter and sort the results, exports the visible rows to CSV, and can clean download-site tags out of PDF filenames.

## Requirements

- Python 3.10 or later
- Tkinter (included with most standard Python installations)
- Optional: `pypdf` for page counts and corruption checks

Install the optional PDF library with:

```bash
python -m pip install pypdf
```

## Run

```bash
python pdf_inventory.py
```

The app does not require a build step.

## Scanning a folder

The app always starts with the folder that contains `pdf_inventory.py` as the target, so you can copy it into a PDF library and start it there. To scan somewhere else, choose a folder with **Browse…** (or **File → Select folder…**); that choice lasts until the app closes. Press **Start scan** to scan the folder and every subfolder.

- **Duplicates** are found by size, then a quick partial hash, then a full SHA-256 comparison. Copies of the same file share a group number ("Yes · group 2"), so sorting by the Duplicate column puts each file next to its copies. The status line shows how much space removing the extra copies would free. Hard links count as one file.
- **Problem** explains why a row is marked Corrupted, Encrypted or Unreadable, using the PDF library's own message. A PDF that takes longer than two minutes to read is reported as unreadable instead of stalling the scan.
- **Skipped folders.** Folder links and junctions are not followed, so nothing is listed twice. System folders such as `C:\Windows`, `$RECYCLE.BIN` and folders without access are skipped too. A library folder that merely has a system-like name, such as `Books\Windows`, is still scanned. After a scan, **Skipped folders (N)** in the status bar lists what was skipped and why.

**Export visible rows** saves the current rows to CSV, including the problem text and the exact size in bytes. Export becomes available when a scan finishes.

## Cleaning PDF filenames

**Tools → Clean PDF filenames…** removes these exact tags from the end of PDF names:

- `(Z-Library)`
- `(z-library.sk, 1lib.sk, z-lib.sk)`

It works on the rows currently visible in the table, so you can narrow the set with the search box first. A preview lists every planned rename. Names that would collide with an existing file, or with another cleaned name, are marked and skipped rather than overwritten. A tag followed by other text, such as `Book (Z-Library)_compressed.pdf`, is left alone. Nothing changes until you press **Rename N files**.

Only names change; file contents are never opened for writing. Every run saves a report, and **Tools → Undo a filename cleanup…** restores the original names from any report, including reports made by the former `pdf_filename_cleaner.py` script.

## Files the app writes

All in the per-user application folder: `%APPDATA%\PDFMasterSuite` on Windows, `~/Library/Application Support/PDFMasterSuite` on macOS, and `~/.config/PDFMasterSuite` on Linux.

- `settings.json`: language, CSV separator, last export folder and window position. A window position that is no longer on any screen is ignored.
- `rename_reports/`: one CSV report per filename cleanup or undo.
- `pdf_inventory.log`: warnings and errors, kept small by rotation.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+O | Select folder |
| Ctrl+R | Start or cancel a scan |
| Ctrl+E | Export visible rows |
| Ctrl+F | Focus the search box |
| Ctrl+A | Select all visible rows |
| Ctrl+Shift+C | Copy the selected file's full path |
| Esc | Clear the search |

Shortcuts also work with Caps Lock on.

## Quality checks

Run the built-in checks with:

```bash
python -m compileall -q pdf_inventory.py test_pdf_inventory.py
```

```bash
python -m unittest -v
```

The same checks run for pull requests and pushes to `main` through GitHub Actions: on Windows with Python 3.10–3.13, plus Windows and Ubuntu jobs with `pypdf` installed.
