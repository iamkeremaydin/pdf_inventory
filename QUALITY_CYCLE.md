# Quality Cycle

This project improves in short, reversible iterations. Each iteration has one theme, a measurable acceptance criterion, and a verification method.

## Current baseline

The app is a local desktop utility. It does not collect analytics or send user data. No support tickets or runtime error logs were available in this repository at the time of this baseline.

| Area | Current measure | Target | Evidence source |
| --- | --- | --- | --- |
| Scan responsiveness | At most 4 active file tasks and 8 submitted tasks | Keep the interface responsive on large folders | Unit test and manual scan |
| UI memory pressure | At most 512 pending worker-to-UI events | No unbounded event backlog | Unit test and code review |
| Core correctness | Compile and unit-test pass | Pass on every pull request and `main` push | GitHub Actions |
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

## Backlog

| Priority | Hypothesis | Owner | Success metric | Effort | Risk | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Show per-file inspection errors on demand so users can act on unreadable PDFs | Repository maintainer | Fewer repeated scans to identify failures | Medium | Low | Scored as O2 in `PDF_INVENTORY_ANALYSIS.md`; planned for Iteration 5 |
| 2 | Virtualize the result table for very large inventories | Repository maintainer | Lower refresh time with 10,000+ files | Medium | Medium | Profiled; the cheaper caching fix (O4) comes first in Iteration 4 |
| 3 | Add an optional scan summary file beside CSV exports | Repository maintainer | Fewer manual summaries after a scan | Small | Low | Validate demand first |
| 4 | Preserve or restore useful filter and sort choices across scans | Repository maintainer | Fewer repeated adjustments | Small | Medium | Needs workflow decision |

The full scored backlog is in `PDF_INVENTORY_ANALYSIS.md` §5. Review the dashboard and backlog after each release. Add new work only when it has an owner, metric, verification method, rollback path, and review date.
