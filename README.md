# PDF Master Suite — Inventory

A free, open-source desktop app that scans folders for PDF files. It shows page counts, sizes and dates, finds duplicates, exports the results to CSV and cleans download-site tags out of filenames. It works offline, never deletes anything, and keeps all its data in a folder next to the program.

Version: MVP 1.0.1 · Windows, macOS and Linux · English and Turkish

## Install

**Download** the build for your system from the [latest release](../../releases/latest) — no Python needed:

| System | File |
| --- | --- |
| Windows | `PDF-Master-Suite-windows-x64.exe` |
| macOS, Apple silicon (M1 and later) | `PDF-Master-Suite-macos-arm64.zip` |
| macOS, Intel | `PDF-Master-Suite-macos-x86_64.zip` |
| Linux (x86-64) | `PDF-Master-Suite-linux-x86_64.tar.gz` |

### First launch: the builds are not code-signed

The app is open source and the downloads are built by GitHub Actions from this repository, but they carry no paid signature, so your system warns you once:

- **Windows:** SmartScreen shows "Windows protected your PC". Click **More info → Run anyway**.
- **macOS:** unzip, move the app anywhere you like, then **right-click it → Open → Open**. If macOS still refuses, run `xattr -d com.apple.quarantine "PDF Master Suite.app"` in Terminal, or use **System Settings → Privacy & Security → Open Anyway**.
- **Linux:** extract the archive and run `./pdf-master-suite` (run `chmod +x pdf-master-suite` first if needed).

**Or run from source** (Python 3.10+ with Tkinter):

```bash
python -m pip install pypdf   # optional: page counts and corruption checks
python pdf_inventory.py
```

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Quality cycle and backlog](docs/QUALITY_CYCLE.md)

## License

[MIT](LICENSE) © Kerem Aydın — [keremaydin.net](https://keremaydin.net)
