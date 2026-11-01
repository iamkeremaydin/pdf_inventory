#!/usr/bin/env python3
"""Safely remove known Z-Library source tags from PDF filenames.

The program never reads or writes PDF content. It only renames matching files
after presenting a preview and receiving explicit confirmation.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import os
import re
import sys
import tempfile
import traceback
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON_EXECUTABLE = re.compile(r"(py|pyw|python[\d.]*w?)\.exe", re.IGNORECASE)
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003

MARKER_SUFFIX = re.compile(
    r"\s*\((?P<marker>z-library|z-library\.sk\s*,\s*1lib\.sk\s*,\s*z-lib\.sk)\)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RenamePlan:
    source: Path
    destination: Path | None
    marker: str | None
    status: str
    detail: str


def cleaned_pdf_name(name: str) -> tuple[str, str] | None:
    """Return the cleaned name and matched marker, or None when no safe match exists."""
    path = Path(name)
    if path.suffix.casefold() != ".pdf":
        return None
    match = MARKER_SUFFIX.search(path.stem)
    if not match:
        return None
    cleaned_stem = MARKER_SUFFIX.sub("", path.stem).rstrip()
    if not cleaned_stem:
        return None
    return cleaned_stem + path.suffix, match.group("marker")


def is_link_or_junction(entry: os.DirEntry[str]) -> bool:
    """True for symlinks and Windows junctions, which can loop back into the scanned tree."""
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)  # Python 3.12+
    if is_junction is not None:
        return bool(is_junction())
    return getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0) == IO_REPARSE_TAG_MOUNT_POINT


def scan_pdf_files(root: Path) -> tuple[list[Path], list[str]]:
    """Collect regular PDFs below root without following directory symlinks or junctions."""
    files: list[Path] = []
    warnings: list[str] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if not is_link_or_junction(entry):
                                stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False) and entry.name.casefold().endswith(".pdf"):
                            files.append(Path(entry.path))
                    except OSError as exc:
                        warnings.append(f"Could not inspect {entry.path}: {exc}")
        except OSError as exc:
            warnings.append(f"Could not scan {directory}: {exc}")
    return sorted(files, key=lambda path: str(path).casefold()), warnings


def plan_renames(pdf_paths: Iterable[Path]) -> list[RenamePlan]:
    """Build a collision-safe rename preview for the supplied PDF paths."""
    plans: list[RenamePlan] = []
    for source in pdf_paths:
        cleaned = cleaned_pdf_name(source.name)
        if not cleaned:
            continue
        name, marker = cleaned
        plans.append(RenamePlan(source, source.with_name(name), marker, "ready", "Ready to rename"))

    by_destination: dict[str, list[int]] = defaultdict(list)
    for index, plan in enumerate(plans):
        if plan.destination:
            by_destination[str(plan.destination).casefold()].append(index)

    resolved: list[RenamePlan] = []
    for index, plan in enumerate(plans):
        assert plan.destination is not None
        if len(by_destination[str(plan.destination).casefold()]) > 1:
            resolved.append(RenamePlan(plan.source, plan.destination, plan.marker, "collision",
                                       "Another matched file has the same cleaned name"))
        elif plan.destination.exists():
            resolved.append(RenamePlan(plan.source, plan.destination, plan.marker, "collision",
                                       "A file with the cleaned name already exists"))
        else:
            resolved.append(plan)
    return resolved


def _move_without_overwrite(source: Path, destination: Path) -> None:
    """Rename without replacing an existing destination or modifying file content."""
    if os.name == "nt":
        if ctypes.windll.kernel32.MoveFileW(str(source), str(destination)) == 0:  # type: ignore[attr-defined]
            error = ctypes.windll.kernel32.GetLastError()  # type: ignore[attr-defined]
            if error in {80, 183}:  # ERROR_FILE_EXISTS / ERROR_ALREADY_EXISTS
                raise FileExistsError(error, os.strerror(error), str(destination))
            raise OSError(error, os.strerror(error), str(destination))
        return

    # A hard-link then unlink is an atomic no-overwrite move within one directory.
    os.link(source, destination)
    try:
        os.unlink(source)
    except OSError:
        try:
            os.unlink(destination)
        except OSError:
            pass
        raise


def apply_renames(plans: Iterable[RenamePlan]) -> list[RenamePlan]:
    """Apply only ready plans and record all results without overwriting files."""
    outcomes: list[RenamePlan] = []
    for plan in plans:
        if plan.status != "ready" or plan.destination is None:
            outcomes.append(plan)
            continue
        if not plan.source.is_file():
            outcomes.append(RenamePlan(plan.source, plan.destination, plan.marker, "skipped",
                                       "Source file is no longer available"))
            continue
        if plan.destination.exists():
            outcomes.append(RenamePlan(plan.source, plan.destination, plan.marker, "collision",
                                       "A file with the cleaned name now exists"))
            continue
        try:
            _move_without_overwrite(plan.source, plan.destination)
        except FileExistsError:
            outcomes.append(RenamePlan(plan.source, plan.destination, plan.marker, "collision",
                                       "A file with the cleaned name now exists"))
        except OSError as exc:
            outcomes.append(RenamePlan(plan.source, plan.destination, plan.marker, "error", str(exc)))
        else:
            outcomes.append(RenamePlan(plan.source, plan.destination, plan.marker, "renamed", "Renamed safely"))
    return outcomes


def write_report(destination: Path, plans: Iterable[RenamePlan]) -> None:
    """Write a CSV report atomically for audit or review."""
    temp_name: str | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False,
                                         dir=destination.parent, suffix=".tmp") as stream:
            temp_name = stream.name
            writer = csv.writer(stream, lineterminator="\r\n")
            writer.writerow(("Status", "Marker", "Source", "Destination", "Detail"))
            for plan in plans:
                writer.writerow(tuple(_safe_csv_cell(value) for value in (
                    plan.status, plan.marker or "", str(plan.source), str(plan.destination or ""), plan.detail,
                )))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
        temp_name = None
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _safe_csv_cell(value: str) -> str:
    """Prevent spreadsheet formula execution when a report is opened in a spreadsheet."""
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def default_report_path(root: Path, prefix: str) -> Path:
    """Return an unused, timestamped report path inside root."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for index in range(1, 10_000):
        suffix = "" if index == 1 else f"_{index}"
        candidate = root / f"{prefix}_{timestamp}{suffix}.csv"
        if not candidate.exists():
            return candidate
    raise OSError("Could not allocate a unique report filename")


def load_undo_plans(report_path: Path) -> tuple[list[RenamePlan], list[str]]:
    """Load only validated completed renames from one of this tool's CSV reports."""
    plans: list[RenamePlan] = []
    warnings: list[str] = []
    required_columns = {"Status", "Marker", "Source", "Destination", "Detail"}
    try:
        with report_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
                return [], ["The report does not have the expected cleaner columns."]
            for row_number, row in enumerate(reader, start=2):
                if row.get("Status") != "renamed":
                    continue
                original = Path(row.get("Source") or "")
                current = Path(row.get("Destination") or "")
                cleaned = cleaned_pdf_name(original.name)
                if (not original.is_absolute() or not current.is_absolute() or original.parent != current.parent
                        or not cleaned or cleaned[0] != current.name):
                    warnings.append(f"Ignored invalid report row {row_number}.")
                    continue
                plans.append(RenamePlan(current, original, row.get("Marker") or None,
                                        "ready", "Ready to restore the original filename"))
    except (OSError, csv.Error, UnicodeError) as exc:
        return [], [f"Could not read report: {exc}"]
    return plans, warnings


def print_summary(plans: list[RenamePlan], dry_run: bool, root: Path | None = None,
                  subject: str = "matching PDF file(s)") -> None:
    counts: dict[str, int] = defaultdict(int)
    for plan in plans:
        counts[plan.status] += 1
    title = "Preview" if dry_run else "Completed"
    print(f"{title}: {len(plans)} {subject}")
    for status in ("ready", "renamed", "collision", "skipped", "error"):
        if counts[status]:
            print(f"  {status}: {counts[status]}")
    if dry_run:
        for plan in plans:
            if plan.status == "ready" and plan.destination:
                try:
                    source = plan.source.relative_to(root) if root else plan.source
                    destination = plan.destination.relative_to(root) if root else plan.destination
                except ValueError:
                    source, destination = plan.source, plan.destination
                print(f"  rename: {source} -> {destination}")
    for plan in plans:
        if plan.status in {"collision", "error", "skipped"}:
            print(f"  {plan.status}: {plan.source} — {plan.detail}")


def launched_without_terminal() -> bool:
    """Return True when Windows opened a console only for this script, e.g. after a double-click.

    Such a console closes as soon as the script exits, so output would vanish unread.
    """
    if os.name != "nt" or not sys.stdin.isatty():
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.QueryFullProcessImageNameW.argtypes = (
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32),
        )
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        pids = (ctypes.c_uint32 * 16)()
        count = kernel32.GetConsoleProcessList(pids, len(pids))
        if not 0 < count <= len(pids):
            return False
        # A shell (cmd, PowerShell, bash) shares the console when run from a terminal.
        for pid in pids[:count]:
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                buffer = ctypes.create_unicode_buffer(32768)
                size = ctypes.c_uint32(len(buffer))
                if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    return False
            finally:
                kernel32.CloseHandle(handle)
            if not PYTHON_EXECUTABLE.fullmatch(Path(buffer.value).name):
                return False
        return True
    except (AttributeError, OSError):
        return False


def pause_before_exit() -> None:
    try:
        input("\nPress Enter to close this window...")
    except (EOFError, KeyboardInterrupt):
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove confirmed Z-Library suffixes from PDF filenames without opening PDFs."
    )
    parser.add_argument("root", nargs="?", default=SCRIPT_DIR, type=Path,
                        help="Folder to scan recursively (default: the folder containing this script).")
    parser.add_argument("--apply", action="store_true", help="Rename files after confirmation.")
    parser.add_argument("--undo", type=Path, metavar="REPORT", help="Restore completed renames from a cleaner report.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt; requires --apply.")
    parser.add_argument("--report", type=Path, help="CSV path for a preview or final audit report.")
    return parser.parse_args(argv)


def run_undo(report_path: Path, output_report: Path | None) -> int:
    plans, warnings = load_undo_plans(report_path.expanduser())
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    if not plans:
        return 1
    print(f"Undo preview: {len(plans)} completed rename(s) from {report_path}.")
    print_summary(plans, dry_run=True, subject="restore operation(s)")
    try:
        answer = input("Type UNDO to restore the ready filenames: ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
        print()
    if answer != "UNDO":
        print("No files were restored.")
        return 0

    outcomes = apply_renames(plans)
    destination = output_report.expanduser() if output_report else default_report_path(
        report_path.expanduser().parent, "pdf_filename_cleaner_undo"
    )
    report_error: OSError | None = None
    try:
        write_report(destination, outcomes)
    except OSError as exc:
        report_error = exc
    print_summary(outcomes, dry_run=False, subject="restore operation(s)")
    if report_error:
        print(f"Could not write undo report: {report_error}", file=sys.stderr)
        return 1
    print(f"Undo report written to {destination.resolve()}.")
    return 1 if any(plan.status == "error" for plan in outcomes) else 0


def main(argv: list[str] | None = None, double_clicked: bool = False) -> int:
    args = parse_args(argv)
    if double_clicked:
        # No way to pass --apply from Explorer; the RENAME confirmation still guards the change.
        args.apply = True
    root = args.root.expanduser()
    if args.undo:
        if args.apply or args.yes:
            print("--undo cannot be combined with --apply or --yes.", file=sys.stderr)
            return 2
        return run_undo(args.undo, args.report)
    if args.yes and not args.apply:
        print("--yes can only be used with --apply.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Folder does not exist or is not accessible: {root}", file=sys.stderr)
        return 2

    print(f"Scanning {root.resolve()} and all subfolders...", flush=True)
    pdf_files, warnings = scan_pdf_files(root)
    plans = plan_renames(pdf_files)
    print(f"Found {len(pdf_files)} PDF file(s).")
    print_summary(plans, dry_run=True, root=root)
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    if not pdf_files:
        print("No PDF files were found. Put this script in the folder that holds your PDFs, "
              f'or pass that folder: python {Path(sys.argv[0]).name} "C:\\Books"')
    elif not plans:
        print("No PDF filename ends with a supported Z-Library tag, so nothing needs renaming.")
    elif not args.apply and any(plan.status == "ready" for plan in plans):
        print("This was a preview; no files were renamed. Run again with --apply to rename them.")

    results = plans
    applied = False
    report_path: Path | None = args.report.expanduser() if args.report else None
    if args.apply and any(plan.status == "ready" for plan in plans):
        confirmed = args.yes
        if not confirmed:
            try:
                answer = input("Type RENAME to apply the ready changes: ")
            except (EOFError, KeyboardInterrupt):
                answer = ""
                print()
            confirmed = answer == "RENAME"
            if not confirmed:
                print("No files were renamed.")
        if confirmed:
            report_path = report_path or default_report_path(root, "pdf_filename_cleaner")
            try:
                write_report(report_path, [])
            except OSError as exc:
                print(f"Could not create the audit report: {exc}", file=sys.stderr)
                return 1
            results = apply_renames(plans)
            applied = True

    # Save outcomes before printing them, so undo still works if the output fails.
    report_error: OSError | None = None
    if report_path:
        try:
            write_report(report_path, results)
        except OSError as exc:
            report_error = exc
    if applied:
        print_summary(results, dry_run=False)
    if report_error:
        print(f"Could not write report: {report_error}", file=sys.stderr)
        return 1
    if report_path:
        print(f"Report written to {report_path.resolve()}.")

    return 1 if any(plan.status == "error" for plan in results) else 0


def entry_point() -> int:
    if not launched_without_terminal():
        return main()
    try:
        return main(double_clicked=True)
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        pause_before_exit()


if __name__ == "__main__":
    raise SystemExit(entry_point())
