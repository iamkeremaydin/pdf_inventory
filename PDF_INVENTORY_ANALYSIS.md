# pdf_inventory.py — in-depth analysis

- **Analysed:** 2026-11-01, at commit `e2c1662`. Line numbers below refer to that commit.
- **Environment:** Windows 11, Python 3.13.14, pypdf 6.21.4.
- **Status:** H1, H2 and L9 (O1, O3) were fixed in Iteration 3; see `QUALITY_CYCLE.md`. Everything else below is still open.

## 1. Summary

`pdf_inventory.py` is a single-file Tkinter desktop app (1,369 lines). It scans a folder tree for PDFs and shows name, folder, size, page count, modified date and a duplicate flag. You can search, sort, filter to duplicates and export the visible rows to CSV.

The concurrency design is sound. The worker never touches Tk, work is bounded and back-pressured, and duplicate detection uses staged hashing with guards against files changing mid-scan.

The weaknesses are in a few specific places rather than spread across the code:

1. **Scan correctness.** Two problems produce silently wrong results:
   - Folder junctions are followed, so files get listed several times and reported as duplicates of themselves.
   - Ordinary folders named `Windows`, `Program Files` and similar are skipped at any depth.
2. **Large-table performance.** With a sort or search active, the table is re-filtered on every 100 ms tick, even when the app is idle.
3. **Results you can't act on.** The reason a file is "Corrupted" is collected but never shown. Duplicates are flagged without saying which files match which.
4. **Test coverage.** Only the helper functions are tested. The scan pipeline is not, and CI never installs pypdf.

Every finding marked **Measured** was reproduced with a script during this analysis (see §7). Findings marked **Reasoned** come from reading the code and were not reproduced.

## 2. Architecture

```
main()
 └─ enable_windows_dpi_awareness() → tk.Tk() → PDFInventoryApp(root) → mainloop()

PDFInventoryApp (1,015 lines, 53 methods)
 ├─ settings: JSON in %APPDATA%/PDFMasterSuite (atomic write, 0600 on POSIX)
 ├─ UI: ttk dark theme, Treeview table, search box, duplicates-only filter, status bar
 ├─ _start_scan ──► thread "PDFInventoryScanner" runs _scan_worker(root)
 │                   1. _discover_pdfs: iterative os.scandir walk, skip-list, progress every 20 folders
 │                   2. inspect: ThreadPool(4), ≤8 in flight, inspect_pdf() → stat + pypdf page count
 │                   3. duplicates: group by size → quick BLAKE2b (first and last 64 KB + size)
 │                                  → full SHA-256 of quick-hash matches; size/mtime re-checked
 │                   events → queue.Queue(maxsize=512)   (worker blocks when full = backpressure)
 └─ _poll_worker_queue every 100 ms: ≤1,200 events per tick → records dict → _refresh_table
                      (incremental insert when unsorted and unfiltered, otherwise full rebuild)
```

**Data model.** `self.records: dict[path, dict]` holds:
- `name`, `folder`, `size_bytes`, `mtime`, `mtime_ns`, `pages`
- `page_state`: ok, pending, unavailable, encrypted, corrupt or unreadable
- `duplicate`: True, False, or None for unknown or pending
- `quick_hash` and `error`

**Module-level helpers (tested):** `normalize_search`, `resolve_csv_delimiter`, `sanitize_csv_cell`, `write_csv_export`, `_quick_hash`, `_full_hash`.

**Not tested:** `inspect_pdf`, plus everything inside the class: discovery, the duplicate pipeline, cancellation, rendering and export wiring.

## 3. Strengths to keep

- **Thread discipline.** The worker communicates only through the queue, and every Tk call happens on the main thread.
- **Bounded resources.**
  - 4 workers with at most 8 tasks in flight in each stage.
  - The UI queue is capped at 512 events, and the main thread processes at most 1,200 per tick.
- **Duplicate detection is correct and cheap.**
  - Only same-size files are hashed.
  - The quick hash narrows candidates, and SHA-256 confirms them.
  - Files that change size or mtime mid-scan become "Unknown" rather than producing a false match.
- **Cancellation.** The cancel flag is checked between tasks and inside the SHA-256 read loop. The status line honestly says "finishing active file operations".
- **Safe writes.** Settings and CSV exports are written to a temporary file, flushed and fsynced, then moved into place with `os.replace`. Exports neutralise formula prefixes (`= + - @`) and use a UTF-8 BOM so Excel opens them correctly.
- **Localisation.** English and Turkish have identical key sets (59 each). Search folds case and diacritics, including the Turkish dotless ı. The CSV separator follows the locale (`;` for Turkish).
- **No network, no PDF writes.** Files are opened read-only, and opening a file uses the OS default handler.
- **DPI awareness** on Windows, with all sizes scaled through `_px`.

## 4. Findings by severity

### High

**H1. Folder junctions are followed: files are listed multiple times and reported as duplicates of themselves.** *Measured. Fixed in Iteration 3.*
- **Where:** `_discover_pdfs`, `pdf_inventory.py:731`.
- **Cause:** On Windows, `DirEntry.is_dir(follow_symlinks=False)` returns True for junctions, which are not symlinks.
- **Effect:** A junction that loops back to its parent made a tree containing one PDF report 64 PDFs across 129 folders, until the path length ran out at 856 characters. All 64 copies would go to hashing and be flagged as duplicates. A junction pointing at a sibling folder (no loop) also double-lists every file in it.
- **Fix:** Skip reparse points, or remember visited `(st_dev, st_ino)` pairs, which also catches hard links (L9). Use `DirEntry.is_junction()` on Python 3.12+, and `st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT` from `entry.stat(follow_symlinks=False)` on 3.10–3.11.
- **Also affects the cleaner:** `scan_pdf_files` in `pdf_filename_cleaner.py` has the same pattern. Its collision checks prevent damage, but a looped file is planned many times.

**H2. The skip-list silently drops user folders with common names, at any depth.** *Measured. Fixed in Iteration 3.*
- **Where:** `SKIP_DIR_NAMES`, `pdf_inventory.py:170` and `:732`.
- **Effect:** `books/Windows/Windows Internals.pdf` was not found, while `books/Linux/Linux Kernel.pdf` was. Any folder named `windows`, `program files`, `programdata`, `perflogs` and so on is skipped wherever it appears. The status line only reports "N folders skipped" and gives no names.
- **Your library:** the current inventory has no affected folder names, so you haven't hit this yet.
- **Fix:**
  - Apply the system names only directly under a drive root, or only to the real system folders (`%SystemRoot%`, `%ProgramFiles%`, `%ProgramData%`). Keep the volume-level names (`$recycle.bin`, `system volume information`, `.Trashes`, …) everywhere.
  - Show the skipped folder names on demand.

### Medium

**M1. Idle CPU use whenever a sort or search is active.** *Measured.*
- **Where:** `_poll_worker_queue` (`:1011`) calls `_update_count_label` (`:1228`) on every 100 ms tick, and that re-runs `_filtered_records()` whenever the table isn't in plain mode.
- **Effect:** With 10,000 rows, each tick costs 54 ms when sorted by name and 80 ms with a search active. That keeps one core 35–45 % busy indefinitely while nothing is happening.
- **Fix:** Store the visible count when the table is refreshed, and only recompute it when the records, query, sort or filter change.

**M2. Search and sorting do a full rebuild with repeated work.** *Measured.*
- **Effect:**
  - One search keystroke costs 584 ms at 10,000 rows.
  - `_apply_search` filters three times: once in `_refresh_table` and twice through `_update_count_label`.
  - `_filtered_records` re-normalises five strings per record on every pass.
  - While a scan runs with a sort active, every tick that brings new rows rebuilds the whole tree.
- **Fix:** Cache a normalised search key per record when the record arrives, and filter once per refresh. While scanning with a sort active, throttle rebuilds (for example to at most one every 500 ms) or insert rows in sorted position.

**M3. The reason a file is "Corrupted" or "Unreadable" is collected and then thrown away.** *Reasoned, confirmed in data.*
- **Where:** `record["error"]` is set in `inspect_pdf` (`:315`, `:317`) but never displayed or exported.
- **Your library:** the real inventory has 4 files marked "Bozuk" (Corrupted), one of them 64 MB. There's no way to tell actual damage from a pypdf parsing limitation.
- **Fix:** Show the error as a tooltip or in a details pane, and add an optional "Problem" column to the export.

**M4. Duplicates aren't grouped, so you can't see which file matches which.** *Reasoned, confirmed in data.*
- **Your library:** the real export flags 7 files as duplicates. They form 3 groups: 2 copies of Kahneman, 3 of Allen Carr and 2 of Frankl. Nothing in the table or the CSV says which file belongs with which.
- **Why the CSV can't help:** it contains only rounded sizes like "431.8 KB", so the groups can't be reliably rebuilt from it.
- **Fix:**
  - Add a duplicate-group column (a short ID, or "1 of 3").
  - Add a "reclaimable space" total to the status line.
  - Add exact byte sizes to the export.

**M5. Parsing a PDF has no time limit.** *Reasoned, not reproduced.*
- **Where:** `inspect_pdf` runs pypdf on worker threads, which cannot be interrupted.
- **Effect:**
  - One pathological PDF can occupy a worker indefinitely, and cancelling waits for it.
  - On close, `concurrent.futures` waits for its worker threads at exit. The window can disappear while `python.exe` keeps running until the queued inspections finish.
- **Fix:** Wait for a real example before building a process pool with timeouts (backlog O11). As a cheap first step, record per-file inspection time so slow files can be spotted.

**M6. The scan pipeline isn't tested, and CI never exercises page counting.** *Measured from the repo.*
- **Gaps:**
  - The 7 inventory tests cover helpers only.
  - `_scan_worker` is the longest function at 198 lines, and it lives inside the Tk class, so it can't be tested without a UI.
  - CI (`tests.yml`) doesn't install pypdf, so the page-count path never runs there.
  - CI is Windows-only, although the README calls the app cross-platform.
- **Fix:**
  - Extract discovery and the duplicate pipeline into Tk-free functions that take a cancel event and a callback.
  - Test them for nested folders, junctions, the skip-list, duplicate groups, files changing mid-scan and cancellation.
  - Add one CI job with pypdf installed.

### Low

- **L1. Two keyboard shortcut bugs.** *Measured.*
  - **Ctrl+Shift+C never fires.** Tk reports Shift+C as the keysym `C`, but the binding is `<Control-Shift-c>` (`:602`).
  - **Caps Lock disables every letter shortcut** (Ctrl+F/O/R/E/A).
  - **Fix:** bind the uppercase variants as well.
- **L2. Zebra striping breaks when rows update during a scan.** *Measured.* In incremental mode, updated rows get their stripe from `len(self._iid_by_path)` (`:1141`) instead of their position. After an update, rows 0–4 showed `even, even, even, even, even`.
- **L3. Dead or no-op code.**
  - The `worker_error` event is handled (`:1004`) but never emitted.
  - The `msg_folder_error` text is never used: opening a folder shows the file error message.
  - `_append_library_warning` and `_queue_table_refresh` are one-line wrappers.
  - `lang_combo.configure(state="readonly")` in `_start_scan` (`:703`) changes nothing.
- **L4. Maintainability.**
  - `_scan_worker` contains three copies of the same bounded-executor loop, about 45 lines each.
  - One class mixes scan orchestration, rendering, settings and export.
  - A single `bounded_map(executor, fn, items, cancel_event, on_result)` helper would remove about 90 lines and make each stage testable.
- **L5. The window can open off-screen.** The saved geometry is restored without checking it against the current screen size, so it can land off-screen after a monitor change.
- **L6. Export quirks.**
  - Exporting is allowed mid-scan and writes "Checking…" placeholders.
  - Size and date are exported as display text, so they don't sort as numbers in a spreadsheet.
- **L7. The README overstates the features.** It says "page counts and metadata", but only page count, size and modified date are read.
- **L8. Errors leave no trace when there's no console.** Errors are logged only to stderr. When the app is started with `pythonw` or by double-clicking, a scanner failure leaves nothing behind except the status line.
- **L9. The same file reached by two paths counts as a duplicate.** This happens with hard links and with the junction case in H1. The `(st_dev, st_ino)` check from H1 fixes both. *Fixed in Iteration 3: junctions are no longer followed, and hard links share one duplicate check.*

### Security

No significant findings. There's no network access and no execution of file content. Paths are passed to `os.startfile` or `open`/`xdg-open` only for discovered `.pdf` files and their folders. CSV formula injection is neutralised, and the settings file is written atomically.

## 5. Scored opportunities

This uses the same method as `PDF_CLEANER_QUALITY.md`:
- **Value, Fit and Confidence** are scored 1–3, higher is better.
- **Effort and Risk** are scored 1–3, higher is worse.
- **Score = V × F × C ÷ (E × R).**
- An item is built now only if it scores ≥ 9 with Confidence 3. Everything else stays a hypothesis.

| ID | Opportunity | Fixes | V | F | C | E | R | Score | Success metric | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| O1 | Don't follow junctions; deduplicate by `(st_dev, st_ino)` | H1, L9 | 3 | 3 | 3 | 1 | 1 | 27 | A junction loop yields each file once; zero self-duplicates | Done in Iteration 3 |
| O2 | Show the corruption or unreadable reason | M3 | 2 | 3 | 3 | 1 | 1 | 18 | Every non-OK row shows its reason in the UI and the export | Iteration 5 |
| O3 | Limit the skip-list to real system locations; list skipped folders | H2 | 3 | 3 | 3 | 1 | 2 | 13.5 | `books/Windows/*.pdf` found; skipped folders visible by name | Done in Iteration 3 |
| O4 | Cache the visible count and normalised search keys; filter once per refresh | M1, M2 | 2 | 3 | 3 | 2 | 1 | 9 | Idle tick < 2 ms and keystroke < 150 ms at 10,000 rows | Following iteration |
| O5 | Duplicate groups and reclaimable space | M4 | 3 | 3 | 2 | 2 | 1 | 9 | Each duplicate shows its group; status shows space to reclaim | After O7 |
| O6 | Shortcut fixes and row-position striping | L1, L2 | 1 | 3 | 3 | 1 | 1 | 9 | All shortcuts work with Shift and Caps Lock; stripes stay alternating | Bundle with O4 |
| O7 | Extract a Tk-free scan pipeline with a `bounded_map` helper, plus tests | M6, L4 | 2 | 3 | 3 | 3 | 2 | 3 | Discovery and duplicate logic covered by tests; `_scan_worker` < 60 lines | Enabler: schedule before O5 |
| O8 | Exact byte size column in the export | L6 | 2 | 2 | 2 | 1 | 2 | 4 | Size sorts numerically in a spreadsheet | Bundle with O5 (changes the CSV format) |
| O9 | Read PDF title and author metadata | L7 | 2 | 2 | 1 | 2 | 2 | 2 | Users search by title or author | Hypothesis: validate demand; until then, fix the README wording |
| O10 | Cache results between scans; skip unchanged files | — | 2 | 2 | 1 | 3 | 2 | 0.67 | A rescan of 10,000 unchanged files takes < 10 % of the first scan | Hypothesis: profile a 10,000-file library first |
| O11 | Inspection timeout through a process pool | M5 | 2 | 2 | 1 | 3 | 2 | 0.67 | A hanging PDF is reported within 30 s and the scan continues | Hypothesis: wait for a real hanging file |
| O12 | Delete or move duplicates from the app | — | 2 | 1 | 1 | 3 | 3 | 0.22 | — | Rejected for now: destructive, outside the app's read-only promise |

O7 scores low on its own, but it is what makes O5 and later work safe to change. That's why it is scheduled as an enabler rather than ranked with the features.

## 6. Proposed iterations (one theme each)

These continue the numbering in `QUALITY_CYCLE.md`, where iterations 1–2 are already recorded.

1. **Iteration 3: correct scan results (O1, O3).**
   - Both changes are in `_discover_pdfs`.
   - Add discovery tests for a junction loop, a sibling junction, a hard link and a `Windows` folder inside a library.
   - Port the junction fix to the cleaner's `scan_pdf_files`.
   - **Verify:** run the probes from §7; expect 1 PDF in the junction case and both PDFs in the skip case.
2. **Iteration 4: responsive large tables (O4, O6).**
   - **Verify:** run the timing probe; target idle tick < 2 ms and keystroke < 150 ms at 10,000 rows. Run the stripe and shortcut probes.
3. **Iteration 5: actionable results (O7, then O2, O5 and O8).**
   - Extract the pipeline first, then add the problem reason, duplicate groups and raw sizes.
   - Announce the CSV column change in the README.

Iterations 3 and 4 are independent and touch different methods.

## 7. How the findings were measured

All probes ran against a temporary folder or a hidden app instance. None of them touched the real PDF library or wrote settings.

| Finding | Probe | Result |
| --- | --- | --- |
| H1 | Junction `books/loop → <root>` (`New-Item -ItemType Junction`), then `PDFInventoryApp._discover_pdfs` | 1 real PDF reported as 64; 129 folders visited |
| H2 | Folders `books/Windows` and `books/Linux`, one PDF each | Only `Linux Kernel.pdf` found; 1 folder skipped |
| M1, M2 | Hidden `PDFInventoryApp` with 10,000 synthetic records; timed `_update_count_label` and `_apply_search` | 0 ms plain; 54 ms sorted; 80 ms searching; 584 ms per keystroke |
| L1 | Focused off-screen Tk window; `event_generate` with `<Control-KeyPress-f>`, `<Control-Shift-KeyPress-C>`, `<Control-KeyPress-F>` | Fired, not fired, not fired |
| L2 | Updated rows 0–4 in incremental mode | Stripes `even,odd,even,odd,even` became `even,even,even,even,even` |
| M3, M4 | Read `pdf_envanteri_20261101_151258.csv` | 4 rows "Bozuk" with no reason; 7 duplicates in 3 unlabelled groups |

Baseline: 17 unit tests pass (7 inventory, 10 cleaner).
