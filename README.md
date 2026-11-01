# PDF Master Suite — Inventory

A cross-platform desktop app for scanning folders of PDF files, inspecting page counts and metadata, finding duplicate files, filtering results, and exporting visible rows to CSV.

## Requirements

- Python 3.10 or later
- Tkinter (included with most standard Python installations)
- Optional: `pypdf` for PDF page counts and inspection

Install the optional PDF library with:

```bash
python -m pip install pypdf
```

## Run

```bash
python pdf_inventory.py
```

The app lets you choose a folder to scan. Duplicate candidates are verified using SHA-256. Use **Export visible rows** to save the current results as a CSV file.

Settings are saved in the operating system's standard per-user application configuration directory. The app does not require a build step.

## PDF filename cleaner

`pdf_filename_cleaner.py` is a separate, standard-library command-line utility. It scans a folder and every subfolder for PDFs, then removes only these exact terminal filename tags:

- `(Z-Library)`
- `(z-library.sk, 1lib.sk, z-lib.sk)`

It does not open, modify, or rewrite PDF contents. The default mode lists every planned rename as a preview. It skips name collisions instead of overwriting a file and does not remove markers that are followed by other filename text.

Without a folder argument it scans the folder that contains the script, wherever it is run from.

On Windows you can also copy the script into your PDF folder and double-click it. It shows the preview, asks you to type `RENAME`, writes an audit report, and keeps the window open until you press Enter. Dropping a folder onto the script scans that folder instead.

```bash
# Preview the script's folder tree
python pdf_filename_cleaner.py

# Preview a different folder
python pdf_filename_cleaner.py "C:\\Books"

# Apply the reviewed renames after typing RENAME
python pdf_filename_cleaner.py "C:\\Books" --apply

# Apply without a prompt. An audit report is created automatically.
python pdf_filename_cleaner.py "C:\\Books" --apply --yes

# Restore completed renames from an audit report after typing UNDO
python pdf_filename_cleaner.py --undo pdf_filename_cleaner_20261101_151258.csv

# Choose where to save a preview, final audit, or undo report
python pdf_filename_cleaner.py "C:\\Books" --report rename-report.csv
```

## Quality checks

Run the built-in checks with:

```bash
python -m compileall -q pdf_inventory.py pdf_filename_cleaner.py test_pdf_inventory.py test_pdf_filename_cleaner.py
python -m unittest -v
```

The same checks run for pull requests and pushes to `main` through GitHub Actions.
