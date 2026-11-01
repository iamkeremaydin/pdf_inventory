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
- **Acceptance:** No unbounded task or event queue; cancellation remains available.
- **Verify:** `python -m unittest -v`; manually scan a large folder and cancel during each scan stage.
- **Rollback:** Revert the iteration commit.
- **Review date:** After the first large-folder scan by a user.

## Backlog

| Priority | Hypothesis | Owner | Success metric | Effort | Risk | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Show per-file inspection errors on demand so users can act on unreadable PDFs | Repository maintainer | Fewer repeated scans to identify failures | Medium | Low | Needs UI design review |
| 2 | Virtualize the result table for very large inventories | Repository maintainer | Lower refresh time with 10,000+ files | Medium | Medium | Profile before implementation |
| 3 | Add an optional scan summary file beside CSV exports | Repository maintainer | Fewer manual summaries after a scan | Small | Low | Validate demand first |
| 4 | Preserve or restore useful filter and sort choices across scans | Repository maintainer | Fewer repeated adjustments | Small | Medium | Needs workflow decision |

Review the dashboard and backlog after each release. Add new work only when it has an owner, metric, verification method, rollback path, and review date.
