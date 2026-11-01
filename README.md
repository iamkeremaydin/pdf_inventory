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

## Quality checks

Run the built-in checks with:

```bash
python -m compileall -q pdf_inventory.py test_pdf_inventory.py
python -m unittest -v
```

The same checks run for pull requests and pushes to `main` through GitHub Actions.
