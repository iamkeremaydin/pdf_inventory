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
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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


def scan_pdf_files(root: Path) -> tuple[list[Path], list[str]]:
    """Collect regular PDFs below root without following directory symlinks."""
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
                writer.writerow((plan.status, plan.marker or "", str(plan.source),
                                 str(plan.destination or ""), plan.detail))
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


def print_summary(plans: list[RenamePlan], dry_run: bool, root: Path | None = None) -> None:
    counts: dict[str, int] = defaultdict(int)
    for plan in plans:
        counts[plan.status] += 1
    title = "Preview" if dry_run else "Completed"
    print(f"{title}: {len(plans)} matching PDF file(s)")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove confirmed Z-Library suffixes from PDF filenames without opening PDFs."
    )
    parser.add_argument("root", nargs="?", default=".", type=Path,
                        help="Folder to scan recursively (default: current folder).")
    parser.add_argument("--apply", action="store_true", help="Rename files after confirmation.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt; requires --apply.")
    parser.add_argument("--report", type=Path, help="Optional CSV path for the preview or final results.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.expanduser()
    if args.yes and not args.apply:
        print("--yes can only be used with --apply.", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"Folder does not exist or is not accessible: {root}", file=sys.stderr)
        return 2

    pdf_files, warnings = scan_pdf_files(root)
    plans = plan_renames(pdf_files)
    print(f"Scanned {len(pdf_files)} PDF file(s) below {root.resolve()}.")
    print_summary(plans, dry_run=True, root=root)
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    results = plans
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
            results = apply_renames(plans)
            print_summary(results, dry_run=False)

    if args.report:
        report_path = args.report.expanduser()
        try:
            write_report(report_path, results)
        except OSError as exc:
            print(f"Could not write report: {exc}", file=sys.stderr)
            return 1
        print(f"Report written to {report_path.resolve()}.")

    return 1 if any(plan.status == "error" for plan in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
