PDF Master Suite — Inventory, MVP 1.0.1.

- New: a download for Intel Macs (`macos-x86_64`), next to the Apple silicon one.
- Every build is now launched once in CI before it is published, so a download that cannot start is never released.
- Project housekeeping only; the app itself is unchanged from MVP 1.0.0.

**Downloads** (no Python needed):

| System | File |
| --- | --- |
| Windows | `PDF-Master-Suite-windows-x64.exe` |
| macOS, Apple silicon (M1 and later) | `PDF-Master-Suite-macos-arm64.zip` |
| macOS, Intel | `PDF-Master-Suite-macos-x86_64.zip` |
| Linux (x86-64) | `PDF-Master-Suite-linux-x86_64.tar.gz` |

**The builds are not code-signed**, so your system warns you the first time:

- **Windows:** SmartScreen "Windows protected your PC" → **More info → Run anyway**.
- **macOS:** right-click the app → **Open** → **Open**. If macOS still refuses, run `xattr -d com.apple.quarantine "PDF Master Suite.app"` in Terminal, or use **System Settings → Privacy & Security → Open Anyway**.
- **Linux:** extract the archive and run `./pdf-master-suite` (`chmod +x pdf-master-suite` first if needed).

Everything the app writes goes into a `pdf_inventory_data` folder next to the program (next to the `.app` on macOS).

## MVP 1.0.0

First public release: folder scan with page counts, sizes and problems; duplicate finder; CSV export; filename cleanup with preview and undo; English and Turkish interface; portable data folder.
