# Quality Cycle

This project improves in short, reversible iterations. Each iteration has one theme, a measurable acceptance criterion, and a verification method.

## Current baseline

The app is a local, portable desktop utility. It does not collect analytics or send user data. Since Iteration 6, its settings, rename reports and log file live in `pdf_inventory_data` next to the program.

| Area | Current measure | Target | Evidence source |
| --- | --- | --- | --- |
| Scan responsiveness | At most 4 active file tasks and 8 submitted tasks; a PDF parse is abandoned after 120 s | Keep the interface responsive on large folders | Unit tests and manual scan |
| Table responsiveness at 10,000 rows | Idle tick 0 ms; search keystroke 26 ms; sort 3 ms | Idle < 2 ms; keystroke < 150 ms | Timing probe in `PDF_INVENTORY_ANALYSIS.md` §7 |
| UI memory pressure | At most 512 pending worker-to-UI events | No unbounded event backlog | Unit test and code review |
| Scan correctness | Junctions not followed; system names skipped only below a drive root; hard links count once | Zero repeated files and zero lost library folders | Unit tests |
| Rename safety | Preview first; no overwrites; every run journaled and reported; undo from any report | Zero overwritten files; every completed rename recoverable | Unit tests |
| Core correctness | 48 unit tests; Windows 3.10–3.13, plus Windows and Ubuntu jobs with pypdf | Pass on every pull request and `main` push | GitHub Actions |
| User friction | Not yet measured | Record a short task-completion check before workflow changes | Manual usability check |

## Iteration record

### Iteration 1 — bounded scan work

- **Owner:** Repository maintainer.
- **Reason:** Large folders could create unbounded background work or pending UI updates.
- **Change:** Limit inspection and hash workers to four, cap submitted work at eight, and cap pending UI events at 512.
- **Foundation:** Add a read-only CI workflow with immutable action revisions and monthly action updates.
- **Acceptance:** No unbounded task or event queue; cancellation remains available.
- **Verify:** `python -m unittest -v`; manually scan a large folder and cancel during each scan stage.
- **Rollback:** Revert the iteration commit.
- **Review date:** After the first large-folder scan by a user.

### Iteration 2 — low-friction, memory-safe export

- **Owner:** Repository maintainer.
- **Reason:** Successful export required dismissing an extra dialog, and large exports duplicated all formatted rows in memory.
- **Change:** Keep success feedback in the status bar and stream sanitized rows through the existing atomic writer.
- **Acceptance:** Export success requires no extra click; the CSV content and formula protection remain intact.
- **Verify:** `python -m unittest -v`; export filtered results and open the CSV in a spreadsheet.
- **Rollback:** Revert the iteration commit.
- **Review date:** After the next user export of a large inventory.

### Iteration 3 — correct scan results

- **Owner:** Repository maintainer.
- **Reason:** The analysis in `PDF_INVENTORY_ANALYSIS.md` (findings H1, H2 and L9) reproduced three ways the scan reported wrong results without warning:
  - **Junctions were followed.** One PDF behind a looping junction was listed 64 times, and two junctions made the number of paths grow exponentially.
  - **Library folders were skipped.** A folder named `Windows` or `Program Files` anywhere in the tree was ignored.
  - **Hard links counted as duplicates.** Two names for one file would be flagged as duplicates of each other.
- **Change:**
  - Discovery skips symlinks and junctions. Python 3.12+ uses `is_junction()`; older versions check the junction reparse tag.
  - Operating-system folder names are skipped only directly below a drive root. Volume bookkeeping folders such as `$RECYCLE.BIN` are still skipped everywhere.
  - Every skipped folder is recorded with its reason (system folder, link or junction, no access). After a scan, a **Skipped folders (N)** button in the status bar lists them.
  - Hard links share one duplicate check, so they inherit one result instead of matching each other.
  - The cleaner's `scan_pdf_files` gets the same junction rule.
- **Acceptance:**
  - A junction loop yields each PDF once and no self-duplicates.
  - `Books/Windows/*.pdf` is found.
  - Hard links alone are not duplicates, but a hard link of a duplicated file is.
  - Skipped folders are visible by name.
- **Success metric:** 0 repeated files and 0 self-duplicates in the junction probe (was 64 copies of 1 file); 0 library folders lost to the skip-list (was all of them).
- **Rollout:** Unit tests and the analysis probes on temporary folders, then a rescan of the real library, comparing against the previous export (159 PDFs, 7 duplicates).
- **Verification result:**
  - 25 unit tests pass, 8 of them new.
  - Disabling junction detection or restoring the old skip rule makes the matching new test fail. The new cleaner test fails against the previous cleaner.
  - Rerunning the analysis probes: the junction tree now yields 1 PDF with the loop listed as a link, and both `Windows Internals.pdf` and `Linux Kernel.pdf` are found.
  - In a hidden window, the skipped-folders button appears only after a scan that skipped folders and shows its count, and the list is capped at 40 entries.
  - The real-library rescan is still pending.
- **Rollback:** Revert the iteration commit.
- **Review date:** 2026-11-15, or after the real-library rescan if sooner.

### Iteration 4 — every remaining analysis finding

This iteration and Iteration 5 were done together at the maintainer's request. They are recorded separately so each has its own acceptance criteria.

- **Owner:** Repository maintainer.
- **Reason:** `PDF_INVENTORY_ANALYSIS.md` still had 6 medium and 8 low findings open after Iteration 3.
- **Change:**
  - **Large tables (M1, M2).** Each record gets one table row, created once and rebuilt only when its data changes. Searching, sorting and filtering only reorder or hide rows. Normalized search keys are cached per record, and the visible count is read from the table instead of being recomputed on every 100 ms tick. While a scan runs, a sorted or filtered view refreshes at most once a second.
  - **Problem column (M3).** Shows the parser's reason for every Corrupted, Encrypted or Unreadable row, and is included in the export.
  - **Duplicate groups (M4).** Groups are numbered ("Yes · group 2"), sorting by the column keeps copies together, and the status line shows reclaimable space. The export adds exact sizes in bytes.
  - **Stuck PDFs (M5).** A parse that runs longer than 120 s is reported as unreadable and the scan moves on. Cancelling no longer waits for running tasks, and closing the window ends the process even if a worker thread is still busy.
  - **Testable pipeline (M6, L4).** Discovery, inspection and duplicate detection are Tk-free module functions (`discover_pdfs`, `scan_folder`). One `bounded_map` helper replaces three copied executor loops. CI adds a Windows job with pypdf and an Ubuntu job.
  - **Shortcuts (L1).** They work with Caps Lock, Ctrl+Shift+C copies the path, and a new File menu shows the accelerators.
  - **Row stripes (L2).** Striping follows row position.
  - **Dead code (L3).** Removed the unused queue event, wrappers and no-op state changes. The folder-open error now uses its own message.
  - **Window position (L5).** A saved position that is off every screen is replaced. Positions on monitors left of the primary one, which were always reset before, are now kept.
  - **Export during scans (L6).** Export is disabled until the scan finishes.
  - **README wording (L7).** The overstated "metadata" claim is gone.
  - **Log file (L8).** Warnings and errors go to `pdf_inventory.log` in the application folder.
- **Acceptance:** Every M and L finding has a test or a recorded probe that fails on the old behavior and passes now.
- **Success metric:** At 10,000 rows, idle tick < 2 ms and search keystroke < 150 ms (were 54–80 ms and 584 ms). Zero hidden corruption reasons; zero unlabelled duplicate groups.
- **Rollout:** Unit tests, the timing and shortcut probes, screenshots of the main window and cleaner dialog, then a rescan of the real library.
- **Verification result:**
  - 44 unit tests pass; one is skipped because pypdf is installed (it covers the no-pypdf path, which CI runs).
  - Timing probe at 10,000 rows: idle tick 0.0 ms in plain, sorted and searched views. Search keystroke 26 ms, or 165 ms for the first search after the data changes. Sort 3 ms. Language switch 260 ms, since every row's text changes.
  - With real keyboard focus, Ctrl+Shift+C copied the selected path and Ctrl+F with the Caps Lock keysym focused the search box.
  - A stuck parse is reported after the timeout while the other files finish (tested with a 0.3 s timeout).
  - Screenshots show the Problem column without horizontal scrolling, "Yes · group 1", the reclaimable-space summary and the Skipped folders button.
  - Not yet verified: the Ubuntu CI job (until the first CI run), and the real-library rescan.
- **Rollback:** Revert the iteration commit.
- **Review date:** 2026-11-15.

### Iteration 5 — filename cleaner inside the app

- **Owner:** Repository maintainer.
- **Reason:** The filename cleaner was a separate command-line script, so users had to leave the app, find the right folder and use the console. The app already knows which PDFs are in the library.
- **Change:**
  - **Tools → Clean PDF filenames…** plans renames for the rows currently visible, so a search narrows the set first. A preview lists every planned rename with its status. Names that would collide are marked and skipped, and nothing changes until **Rename N files** is pressed.
  - Renamed rows keep their place in the table under their new names.
  - Every run writes a report to `rename_reports/` in the application folder, appending each rename as it happens. **Tools → Undo a filename cleanup…** previews and restores from any report, including reports from the former script.
  - `pdf_filename_cleaner.py` and its tests were removed. Their rules and tests now live in `pdf_inventory.py` and `test_pdf_inventory.py`.
- **Acceptance:**
  - The same two tags are removed, with the same collision, bytes-unchanged and undo guarantees as the script.
  - Old reports still undo.
  - No rename happens if the report cannot be created.
  - A crash mid-run leaves the completed renames in the report.
- **Success metric:** Cleaning a library takes one menu action and one confirmation, with no console. 100% of completed renames are recoverable from the report.
- **Rollout:** Unit tests, an end-to-end clean-and-undo test through the app, screenshots in both languages, then a first real cleanup of the library (85 expected matches) followed by a spot check of the report.
- **Verification result:**
  - The end-to-end test renames two tagged files across folders through the app, shows the new names in the table, writes one report, and restores the originals through the undo flow.
  - The visible-rows-only test confirms that a search limits the plan.
  - A test confirms that shortcuts are ignored while the dialog is open.
  - Disabling journaling makes the crash test fail.
  - **Real library, 2026-11-01:** the first cleanup renamed 85 of 85 files, matching the 85 matches the inventory export predicted, and saved its undo report. A spot check of the renamed files is still with the user.
- **Rollback:** Revert the iteration commit. Undo any renames first with **Tools → Undo a filename cleanup…**, or with the restored script's `--undo` option.
- **Review date:** 2026-11-15, or after the first real cleanup if sooner.

### Iteration 6 — fully portable

- **Owner:** Repository maintainer.
- **Reason:** The user copies the program into a library and starts it there. Settings, rename reports and the log still went to `%APPDATA%\PDFMasterSuite`, away from the program and the library they belong to.
- **Change:**
  - All app data goes into `pdf_inventory_data` next to the program (next to the executable when packaged). Nothing is written to per-user folders, with no fallback.
  - One `program_dir()` function decides both the start folder and the data folder.
  - `.gitignore` excludes the data folder so running from the repository leaves the tree clean.
- **Acceptance:**
  - Settings, reports and log resolve inside `pdf_inventory_data` for both the script and a packaged executable.
  - No code path reads `%APPDATA%`, `XDG_CONFIG_HOME` or `~/Library`.
- **Success metric:** 0 files written outside the program folder during a launch, scan and cleanup.
- **Rollout:** Unit tests, then a real launch from the repository confirming that the data folder appears next to `pdf_inventory.py`.
- **Verification result:**
  - 48 unit tests pass (one skipped because pypdf is installed), including new tests for the script and packaged-executable data paths.
  - A copy of `pdf_inventory.py` launched through `main()` from a temporary folder started there and wrote `settings.json` and `pdf_inventory.log` into `pdf_inventory_data` beside it.
  - `%APPDATA%\PDFMasterSuite` received no new or changed files.
- **Known limit:** In a read-only program folder, settings are not saved and cleanup refuses to rename, because the undo report cannot be written. This was chosen over a hidden fallback location.
- **Migration:** Reports from earlier versions stay in `%APPDATA%\PDFMasterSuite\rename_reports` and still undo through the file picker; nothing is moved automatically.
- **Rollback:** Revert the iteration commit.
- **Review date:** 2026-11-15.

### Iteration 7 — public MVP 1.0.0 release

- **Owner:** Repository maintainer.
- **Reason:** The project is going public as open source and users without Python need a download for their system.
- **Change:**
  - Version `MVP 1.0.0` (`APP_VERSION`), shown in **Help → About…**.
  - MIT `LICENSE`; a short `README.md`; all other documents under `docs/` (the former long README is `docs/USER_GUIDE.md`).
  - A Release workflow builds unsigned Windows, macOS and Linux downloads with PyInstaller when a `v*` tag is pushed.
  - A packaged macOS `.app` keeps `pdf_inventory_data` next to the bundle, not inside it, through `program_dir()`.
- **Acceptance:**
  - The tag must match `APP_VERSION` or the release is not created.
  - The release carries one file per system.
- **Verification:** Unit tests (including the macOS bundle path and version); the release run on GitHub.
- **Known limit:** Builds are unsigned (backlog item G stays open for signing).
- **Rollback:** Delete the release and tag; revert the iteration commit.
- **Review date:** 2026-11-25.

### Iteration 8 — release hardening (MVP 1.0.1)

- **Owner:** Repository maintainer.
- **Reason:** After the first public release: Intel Mac users had no download, built programs were never launched before publishing, and the commit history exposed a personal e-mail address.
- **Change:**
  - Release workflow builds `macos-x86_64` on an Intel runner next to `macos-arm64`.
  - New `--smoke-test` flag (with `--require-pdf-library`): opens the real window, closes it itself and reports the result as the exit code. The workflow launches each shipped file this way (Xvfb on Linux), checks that the data folder appears next to the program, and creates the release only if all builds pass.
  - Unsigned-build instructions (SmartScreen, Gatekeeper) in the README and release notes.
  - History rewritten once to replace the personal e-mail with the GitHub no-reply address; `CLAUDE.md` lost a local path (now in the git-ignored `CLAUDE.local.md`).
- **Acceptance:** Four downloads on the release; every smoke test passes; no personal e-mail in the history.
- **Verification:** Unit tests for the flag; the release run on GitHub.
- **Known limit:** Builds are still unsigned. The Intel build is untested on real hardware beyond the CI launch. Old commit SHAs may stay reachable on GitHub until GitHub purges them.
- **Rollback:** Delete the v1.0.1 release and tag; revert the commit.
- **Review date:** 2026-11-25.

## Filename cleaner history

Before Iteration 5, the cleaner was a separate script with its own quality log (`PDF_CLEANER_QUALITY.md`, removed with the script; see the git history).

1. **Recoverable rename runs.** Automatic audit reports and validated undo.
2. **A first run that visibly works.** Scan the script's folder, state every outcome, and handle double-click launches.
3. **Recovery survives failed output.** Write the report before printing results.

Its findings, as they stand now:

| Severity | Finding | Disposition |
| --- | --- | --- |
| High | Applied renames had no default recovery record | Fixed (cleaner iteration 1); kept in the app |
| Medium | A hand-edited report could attempt unrelated file moves | Fixed: only same-folder pairs matching the cleaning rule are accepted; kept in the app |
| Medium | Failed output after renaming left an empty audit report | Fixed (cleaner iteration 3); in the app, the report is written before any UI update |
| Medium | Very large trees were collected in memory before collision planning | Closed: the app plans from records it already holds |
| Low | An interrupt during the rename loop recorded none of that run's renames | Fixed in Iteration 5: each rename is appended to the report as it happens |
| Low | Scanning followed folder junctions | Fixed in Iteration 3 |
| Low | No persistent error monitoring | Partly addressed: local log file since Iteration 4; no telemetry, by design |

## Backlog

Scoring follows `PDF_INVENTORY_ANALYSIS.md` (same folder) §5:
- **Value, Fit and Confidence** are scored 1–3, higher is better.
- **Effort and Risk** are scored 1–3, higher is worse.
- **Score = V × F × C ÷ (E × R).**

| ID | Hypothesis | Owner | Score | Success metric | Decision |
| --- | --- | --- | --- | --- | --- |
| O9 | Reading PDF title and author lets users search by them | Repository maintainer | 2 | Users find books by title or author | Validate demand first |
| O10 | Caching results between scans makes rescans fast | Repository maintainer | 0.67 | A rescan of 10,000 unchanged files takes < 10 % of the first scan | Profile a 10,000-file library first |
| O11 | Inspecting in separate processes would also free the worker a stuck parse occupies | Repository maintainer | 0.67 | A stuck parse costs no capacity | Wait for a real stuck file; the 120 s watchdog covers the visible symptom |
| E | Cleaning tag variants such as `-z-lib.org_` helps more libraries | Repository maintainer | 0.67 | Variant names cleaned with zero false-positive renames in preview | Wait for more examples (2 of 159 today) |
| F | Choosing which tag to remove helps mixed libraries | Repository maintainer | 2 | Fewer unintended exclusions | Wait for a real example |
| G | A signed standalone executable reduces setup friction | Repository maintainer | 1.33 | Faster first successful run | Needs a release and signing decision |
| S1 | An optional scan summary file beside CSV exports saves manual summaries | Repository maintainer | — | Fewer manual summaries after a scan | Validate demand first |
| S2 | Keeping filter and sort choices across scans saves adjustments | Repository maintainer | — | Fewer repeated adjustments | Needs a workflow decision |
| O12 | Deleting or moving duplicates from the app | Repository maintainer | 0.22 | — | Rejected for now: destructive, outside the app's promise |

Closed since the last review:
- Table virtualization: measured; Iteration 4's row reuse already meets the target.
- Per-file inspection errors: the Problem column (Iteration 4).
- The cleaner's console encoding, progress and folder-picker items: obsolete without a console.

Review the dashboard and backlog after each release. Add new work only when it has an owner, metric, verification method, rollback path, and review date.
