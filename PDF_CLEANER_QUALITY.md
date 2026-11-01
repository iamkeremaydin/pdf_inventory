# PDF filename cleaner quality cycle

## Scope and baseline

The cleaner removes two confirmed source tags from the end of PDF filenames. It does not inspect or modify PDF content. The available inventory export contains 159 PDFs, with 85 safe filename matches across 14 folders. Analytics, support tickets, and runtime error logs are not available for this local utility.

| Measure | Baseline | Target | Verification |
| --- | --- | --- | --- |
| Rename steps | Preview, confirm, rename | Keep three deliberate steps | Manual usability check |
| Content changes | No PDF writes | Zero PDF writes | Unit test and code review |
| Collision loss | No overwrite protection | Zero overwritten files | Collision test |
| Recovery | Manual reverse rename | Report-guided undo | Apply and undo test |

## Iteration 1 — recoverable rename runs

- **Owner:** Repository maintainer.
- **Reason:** A rename without an audit record is hard to reverse accurately.
- **Change:** Create an audit CSV automatically for applied runs and add validated, confirmed undo from that report.
- **Acceptance:** Every applied run produces a report. Undo restores only tool-created rename pairs and skips conflicts.
- **Verify:** Run the unit tests and perform a temporary-folder apply/undo check.
- **Rollback:** Do not apply the preview, or run the generated undo report.
- **Review date:** After the first user-run cleanup.

## Finding register

| Severity | Finding | Disposition |
| --- | --- | --- |
| High | Applied renames had no default recovery record | Fixed with automatic audit reports and validated undo |
| Medium | A hand-edited report could attempt unrelated file moves | Fixed by accepting only same-folder pairs that match the tool's exact cleaning rule |
| Medium | Very large trees are collected in memory before collision planning | Profile a 10,000-file library before changing the safe planning model |
| Low | No persistent telemetry or external error monitoring | Deliberately deferred for this local, privacy-preserving utility; audit reports retain operation outcomes |

## Backlog

| Priority | Hypothesis | Owner | Success metric | Effort | Risk | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | A small GUI folder picker will reduce command-line setup errors | Fewer invalid-folder errors | Repository maintainer | Medium | Medium | Validate demand first |
| 2 | A per-marker selection option helps users control mixed libraries | Fewer unintended exclusions | Repository maintainer | Small | Low | Add only after real examples require it |
| 3 | A signed standalone executable reduces setup friction | Faster first successful run | Repository maintainer | Medium | Medium | Requires release and signing decision |
