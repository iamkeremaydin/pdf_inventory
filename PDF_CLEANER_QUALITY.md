# PDF filename cleaner quality cycle

## Scope and baseline

The cleaner removes two confirmed source tags from the end of PDF filenames. It does not inspect or modify PDF content. The available inventory export contains 159 PDFs, with 85 safe filename matches across 14 folders. Analytics, support tickets, and runtime error logs are not available for this local utility.

| Measure | Baseline | Target | Verification |
| --- | --- | --- | --- |
| Rename steps | Preview, confirm, rename | Keep three deliberate steps | Manual usability check |
| Content changes | No PDF writes | Zero PDF writes | Unit test and code review |
| Collision loss | No overwrite protection | Zero overwritten files | Collision test |
| Recovery | Manual reverse rename | Report-guided undo | Apply and undo test |
| First run | Scanned the working directory; double-click output vanished | Script folder by default; every run states its outcome | Temporary-folder run and double-click check |

## Dashboard

| Area | Current | Source |
| --- | --- | --- |
| UX | Double-click flow shipped; first real-library run not yet observed | User report after the first run |
| Reliability | 17 unit tests pass; recovery covered for apply, undo, and failed output | `python -m unittest -v` |
| Opportunity throughput | 1 of 8 scored opportunities implemented this cycle; 1 closed as superseded | Scored backlog below |

## Iteration 1 — recoverable rename runs

- **Owner:** Repository maintainer.
- **Reason:** A rename without an audit record is hard to reverse accurately.
- **Change:** Create an audit CSV automatically for applied runs and add validated, confirmed undo from that report.
- **Acceptance:** Every applied run produces a report. Undo restores only tool-created rename pairs and skips conflicts.
- **Success metric:** 100% of applied runs create an audit report; the apply-and-undo test restores the original name and bytes.
- **Rollout:** Run a preview, apply the cleaner to a temporary folder, then run undo from its generated report before using a real library.
- **Verify:** Run the unit tests and perform a temporary-folder apply/undo check.
- **Verification result:** 13 unit tests pass. A temporary-folder run renamed both markers across a nested folder, created its audit report automatically, and undo restored both original filenames and bytes.
- **Rollback:** Do not apply the preview, or run the generated undo report.
- **Review date:** After the first user-run cleanup.

## Iteration 2 — a first run that visibly works

- **Owner:** Repository maintainer.
- **Reason:** Users reported that running the script on Windows did nothing. It scanned the working directory instead of its own folder, a preview gave no hint that nothing was renamed, and a double-clicked console closed before its output could be read.
- **Change:** Default the scan to the script's folder, print a scanning line and an outcome line for empty, no-match, and preview-only runs, and give double-click launches a `RENAME` prompt and a closing pause (commit `eb87e52`).
- **Acceptance:** With no arguments, the script scans its own folder from any working directory. Every run ends with a line that states what happened. A double-click run previews, requires `RENAME`, and waits for Enter.
- **Success metric:** The first double-click run in the real library previews its 85 matches and completes without command-line help; zero further "nothing happens" reports.
- **Rollout:** Temporary-folder runs, then a preview of the real library, then a double-click apply in it.
- **Verification result:** 16 unit tests pass. From another working directory, a temporary tree found 4 PDFs, previewed 3, and renamed 3 with an audit report. Console detection returned true for Python alone and false under `cmd`. The `py` launcher is not installed on the test machine, so that launch path is untested. The real-library run is still pending.
- **Rollback:** Revert `eb87e52`; restore any renames with `--undo` and the run's audit report.
- **Review date:** 2026-11-15, or after the first real-library run if sooner.

## Iteration 3 — recovery survives failed output

- **Owner:** Repository maintainer.
- **Reason:** Audit rows were written only after the completed summary printed. If that output failed (Ctrl+C, or a filename the console cannot encode when output is redirected), the files were already renamed but the report held only its header, so undo had nothing to restore. A test reproduced this before the fix.
- **Change:** Apply and undo runs write their report before printing the completed summary. A report-write error is still shown, after the summary.
- **Acceptance:** The new failed-output test passes; preview, apply, and undo output is otherwise unchanged.
- **Success metric:** 100% of completed renames appear in the audit report when output after renaming fails (previously 0%).
- **Rollout:** Unit tests, a temporary-folder apply and undo, then the next real run.
- **Verification result:** 17 unit tests pass, including the reproduction, which failed before the change. A temporary-folder apply renamed 3 files across nested folders with 3 audit rows, and undo restored all 3 original names and bytes.
- **Rollback:** Revert the iteration commit.
- **Review date:** 2026-11-15.

## Finding register

| Severity | Finding | Disposition |
| --- | --- | --- |
| High | Applied renames had no default recovery record | Fixed with automatic audit reports and validated undo |
| Medium | A hand-edited report could attempt unrelated file moves | Fixed by accepting only same-folder pairs that match the tool's exact cleaning rule |
| Medium | Failed output after renaming left an empty audit report | Fixed in Iteration 3 |
| Medium | Very large trees are collected in memory before collision planning | Profile a 10,000-file library before changing the safe planning model |
| Low | An interrupt during the rename loop records none of that run's completed renames | Backlog item B |
| Low | No persistent telemetry or external error monitoring | Deliberately deferred for this local, privacy-preserving utility; audit reports retain operation outcomes |

## Scored backlog

Each opportunity is scored 1–3 on **Value** (user benefit), **Fit** (product goal and current architecture), and **Confidence** (strength of evidence), and 1–3 on **Effort** and **Risk** (including maintainability cost), where higher is worse.

**Score = Value × Fit × Confidence ÷ (Effort × Risk)**, from 0.04 to 27.

Implement now only when the score is at least 9, Effort is 1, and Confidence is 3. Record everything else as a hypothesis with a success metric.

| ID | Opportunity | Evidence | V | F | C | E | R | Score | Success metric | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Write the audit report before printing results | Reproduced: failed output left a header-only report | 3 | 3 | 3 | 1 | 1 | 27 | 100% of completed renames recorded despite failed output | Done in Iteration 3 |
| B | Record each rename as it happens | An interrupt mid-loop loses that run's audit rows; 85 renames finish in under a second, so the window is small | 2 | 3 | 2 | 2 | 1 | 6 | An interrupted apply leaves a report listing every completed rename | Next candidate; review 2026-11-15 |
| C | Replace characters the console cannot encode instead of crashing | 0 of 159 names are outside cp1254, the redirected-output encoding; Iteration 3 already protects the audit | 1 | 2 | 3 | 1 | 1 | 6 | No crash with redirected output for any filename | Park until a name fails |
| D | Progress counter during long scans | 159 files across the library scan instantly | 1 | 3 | 2 | 1 | 1 | 6 | Visible progress at least every 2 seconds on 10,000 files | Revisit with the 10,000-file profile |
| E | Clean tag variants such as `-z-lib.org_` and `(Z-Library)_compressed` | 2 of 159 names (1.3%); the rule deliberately skips markers followed by other text | 1 | 2 | 1 | 1 | 3 | 0.67 | Variant names cleaned with zero false-positive renames in preview | Park until more examples; each variant needs a preview test |
| F | Per-marker selection option | Both tags appear in the same library; no request to keep either | 1 | 2 | 1 | 1 | 1 | 2 | Fewer unintended exclusions | Park until a real example requires it |
| G | Signed standalone executable | Python is required today; no setup-failure reports yet | 2 | 2 | 2 | 3 | 2 | 1.33 | Faster first successful run | Requires a release and signing decision |
| H | Small GUI folder picker | Superseded: script-folder default, double-click, and folder drag-and-drop shipped in Iteration 2 | 1 | 2 | 1 | 2 | 2 | 0.5 | Fewer invalid-folder errors | Closed; reopen if users still cannot target the right folder |

Do not start a new iteration until Iteration 2's real-library run has been reviewed.
