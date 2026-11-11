# UI improvement plan — main window

Status: implemented, awaiting approval.

## What the current window gets wrong

Screenshots of the window before this change (English and Turkish, after a 16-file scan) showed:

| # | Problem | Why it matters |
| --- | --- | --- |
| 1 | Four filled button colours (green Start scan, teal Export, blue Clean, grey Browse/Undo) | Every button shouts. Colour no longer tells the user which action is the main one. |
| 2 | Language and CSV separator sit in the main toolbar, next to Start scan | They are set once and rarely touched, yet take prime space and push the scan flow onto a second row. |
| 3 | The flow is split over three rows: folder (row 1), scan (row 2, right), speed (row 3, right) | Choose folder → set speed → scan is one task but the eye zig-zags across the window to do it. |
| 4 | Clean filenames and Export sit far from the search box, although both act on *the rows the search leaves visible* | The connection between "filter" and "act on what's shown" is invisible. |
| 5 | Search is a bare box with a "Search" label, a full-width Clear button, and an unused placeholder text | Takes room, and the `search_hint` text was never shown. |
| 6 | The Duplicates only checkbox and the combobox arrows render with light-grey Tk defaults | Breaks the dark theme; looks unfinished. |
| 7 | Size and Pages are centred; headings are centred over left-aligned text | Numbers are hard to compare when their digits don't line up. |
| 8 | A light border surrounds the table and the scrollbars are light grey | Same theme break as 6. |
| 9 | The progress bar stays full and bright blue after every scan | Looks like something is still running. |
| 10 | No icons anywhere, and the window uses Tk's default feather icon | Buttons need reading instead of recognising; the app looks generic in the taskbar. |
| 11 | Empty table on start gives no hint what to do | First-run users see a blank grid. |

## Principles used

- **One primary action.** Only Start scan is filled with the accent colour (it turns red as Cancel scan while running). All other buttons are quiet secondary buttons (Windows Fluent and macOS HIG both reserve the accent for the default action).
- **Order follows the task.** Left to right: where → how fast → go.
- **Proximity = relationship.** Controls that act on the visible rows sit on the same bar as the controls that decide which rows are visible.
- **Frequency decides prominence.** Set-once preferences move behind a gear button and into the Tools menu.
- **Icons plus text for main actions, icon-only plus tooltip for rare or universally understood ones** (Undo, Settings).
- **Numbers right-aligned, text left-aligned, headings aligned with their column.**
- **Show state only while it is true** (progress bar only during a scan; Skipped folders only when something was skipped; empty-table hint only when empty).

## New layout

```
┌ File  Tools  Help ───────────────────────────────────────────────────────────────┐
│ Target folder [ C:\Books\…                         ] [📁 Browse…]  ⏲ [Medium·6 ▾] [▶ Start scan] [⚙] │  command bar
├──────────────────────────────────────────────────────────────────────────────────┤
│ [🔍 Name, folder or path…      ×]  ☐ Duplicates only        [⌫ Clean names…][↶] [⇥ Export CSV] │  view bar
├──────────────────────────────────────────────────────────────────────────────────┤
│  File name        Folder      Size  Pages  Modified          Duplicate   Problem   Full path │
│  …                                                                                │  table
├──────────────────────────────────────────────────────────────────────────────────┤
│ Done: 16 PDFs · 5 duplicates …       [⚠ Skipped folders (2)]   16 shown / 16 total  [■■■■  ] │  status bar
│                                         Open-source project by Kerem Aydın · keremaydin.net │  credit
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **Command bar** (panel colour): folder field, Browse, resource level (gauge icon + list), Start/Cancel scan, Settings (gear). The gear opens a menu with Language and CSV separator; the same two choices are also under **Tools**.
- **View bar** (window colour, sits directly above the table): search field with a magnifier, placeholder text and an inline × that appears only when there is text; Duplicates only; then — right-aligned — Clean names…, Undo (icon only) and Export CSV.
- **Status bar**: message, Skipped folders (only when non-zero), row count (moved from the view bar), progress bar (only while scanning).

## Icons

Drawn at run time from a small vector set (no image files, no new dependency), anti-aliased, sized to the display scale so they stay sharp at 100–200 %. Each has a dimmed variant for the disabled state.

| Action | Icon | Reason |
| --- | --- | --- |
| Browse | Folder | Universal "pick a folder" metaphor |
| Start scan / Cancel scan | Play ▶ / Stop ■ | Start and stop a long-running job |
| Resource usage | Gauge | Speed / load, not a setting page |
| Settings | Gear | Universal preferences symbol |
| Search | Magnifier, × to clear | Standard search-field anatomy |
| Clean names | Eraser | Removes text from names |
| Undo cleanup | Counter-clockwise arrow | Standard undo |
| Export CSV | Document with outgoing arrow | Data leaves the app as a file |
| Skipped folders | Warning triangle | Something needs attention |
| Window / taskbar | Red PDF document | Recognisable app identity |

Every icon button has a tooltip with the full action name and its shortcut.

## Other polish

- Dark styling for the checkbox, combobox arrows, scrollbars and table border.
- Colours gathered in one `COLORS` palette instead of hex values spread through the code.
- Shorter button labels where an icon carries meaning (Clean names…, Export CSV); menus keep the full wording.
- Empty-table hint: "Choose a folder, then press Start scan (Ctrl+R)." / "No PDF files were found in the selected folder."

## Out of scope (possible follow-ups)

- Per-row status icons in the table (would need the name moved into Tk's tree column).
- A light theme / following the OS theme.
- Saving column widths and sort order between sessions.
