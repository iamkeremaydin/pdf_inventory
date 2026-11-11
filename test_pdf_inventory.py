import csv
import io
import json
import os
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

import pdf_inventory as inv
from pdf_inventory import (
    MAX_IN_FLIGHT_PER_WORKER,
    MAX_UI_QUEUE_EVENTS,
    RESOURCE_LEVELS,
    RenamePlan,
    ResourceGovernor,
    _full_hash,
    _quick_hash,
    apply_renames,
    bounded_map,
    cleaned_pdf_name,
    discover_pdfs,
    geometry_is_visible,
    inspect_pdf,
    is_link_or_junction,
    load_undo_plans,
    normalize_search,
    one_line,
    plan_renames,
    preflight_renames,
    resolve_csv_delimiter,
    resource_profile,
    run_renames,
    sanitize_csv_cell,
    scan_folder,
    skip_reason,
    write_csv_export,
    write_rename_report,
)


def make_junction(link: Path, target: Path) -> None:
    import _winapi

    _winapi.CreateJunction(str(target), str(link))


def discover(root: Path):
    return discover_pdfs(root, threading.Event(), lambda *_args: None)


def run_scan(root: Path) -> list:
    """Run the scan pipeline without Tk and return the events it would send to the UI."""
    events: list = []
    scan_folder(root, threading.Event(), lambda kind, payload: events.append((kind, payload)))
    return events


def final_duplicates(events: list) -> dict:
    return next(payload for kind, payload in events if kind == "duplicates")


def final_records(events: list) -> dict:
    records = {}
    for kind, payload in events:
        if kind in {"file", "file_update"}:
            records[payload["name"]] = payload
    return records


def destroy_root(root: tk.Tk) -> None:
    """Let pending idle events such as ttk's theme change run before the interpreter goes away."""
    root.update()
    root.destroy()


class EntryWithoutJunctionCheck:
    """Mimic os.DirEntry on Python 3.10 and 3.11, which have no is_junction()."""

    def __init__(self, entry):
        self._entry = entry

    def is_symlink(self):
        return self._entry.is_symlink()

    def stat(self, *, follow_symlinks=True):
        return self._entry.stat(follow_symlinks=follow_symlinks)


class InventoryHelpersTest(unittest.TestCase):
    def test_scan_concurrency_is_bounded(self):
        self.assertEqual(MAX_IN_FLIGHT_PER_WORKER, 2)
        self.assertEqual(MAX_UI_QUEUE_EVENTS, 512)


class ResourceLevelTest(unittest.TestCase):
    def test_levels_scale_with_the_cpu_count_and_stay_ordered(self):
        for cpus in (1, 2, 4, 8, 16, 64):
            low, medium, high = (resource_profile(level, cpus) for level in RESOURCE_LEVELS)
            self.assertGreaterEqual(low.workers, 1)
            self.assertLessEqual(low.workers, medium.workers)
            self.assertLessEqual(medium.workers, high.workers)
            self.assertLessEqual(high.workers, 16)
            self.assertLess(low.hash_chunk, medium.hash_chunk)
            self.assertLess(medium.hash_chunk, high.hash_chunk)
            self.assertTrue(low.background_priority)
            self.assertFalse(medium.background_priority or high.background_priority)
        self.assertEqual(resource_profile("medium", 8).workers, 4)
        self.assertEqual(resource_profile("high", 8).workers, 8)
        self.assertEqual(resource_profile("low", 2).workers, 1)

    def test_governor_defaults_to_medium_and_changes_priority_only_when_needed(self):
        governor = ResourceGovernor(cpus=8)
        self.assertEqual(governor.level, "medium")
        self.assertEqual(ResourceGovernor("bogus", cpus=8).level, "medium")
        with mock.patch.object(inv, "apply_process_priority") as priority:
            governor.set_level("high")
            priority.assert_not_called()
            governor.set_level("low")
            priority.assert_called_once_with(True)
            governor.set_level("medium")
            priority.assert_called_with(False)
        with self.assertRaises(ValueError):
            governor.set_level("turbo")

    def test_bounded_map_never_runs_more_tasks_than_the_level_allows(self):
        governor = ResourceGovernor("low", cpus=8)
        lock = threading.Lock()
        running = peak = 0

        def work(item):
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.01)
            with lock:
                running -= 1
            return item

        results = []
        self.assertTrue(bounded_map(work, range(30), threading.Event(),
                                    lambda item, result, error: results.append(result), governor=governor))
        self.assertEqual(sorted(results), list(range(30)))
        self.assertLessEqual(peak, resource_profile("low", 8).workers)

    def test_a_level_change_applies_to_a_running_map(self):
        governor = ResourceGovernor("low", cpus=8)
        names: set = set()
        results = []

        def work(item):
            names.add(threading.current_thread().name)
            time.sleep(0.005)
            return item

        def on_result(item, result, error):
            results.append(result)
            if len(results) == 5:
                governor.set_level("high")

        with mock.patch.object(inv, "apply_process_priority"):
            self.assertTrue(bounded_map(work, range(60), threading.Event(), on_result, governor=governor))
        self.assertEqual(sorted(results), list(range(60)))
        self.assertGreater(len(names), resource_profile("low", 8).workers)

    def test_hashes_are_stable_and_full_hash_honors_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.pdf"
            path.write_bytes(b"PDF inventory test data")
            stat = path.stat()

            self.assertIsNotNone(_quick_hash(path, stat.st_size, stat.st_mtime_ns))
            self.assertIsNotNone(_full_hash(path, stat.st_size, stat.st_mtime_ns))

            cancelled = threading.Event()
            cancelled.set()
            self.assertIsNone(
                _full_hash(Path(directory) / "missing.pdf", stat.st_size, stat.st_mtime_ns, cancelled)
            )

    def test_search_normalization_handles_turkish_and_diacritics(self):
        self.assertEqual(normalize_search("İstanbul ıŞık café"), "istanbul isik cafe")

    def test_csv_delimiter_respects_locale_and_explicit_choice(self):
        self.assertEqual(resolve_csv_delimiter("auto", "tr"), ";")
        self.assertEqual(resolve_csv_delimiter("tab", "en"), "\t")

    def test_csv_formula_prefix_is_neutralized(self):
        self.assertEqual(sanitize_csv_cell("  =1+1"), "'  =1+1")
        self.assertEqual(sanitize_csv_cell(42), 42)

    def test_translations_have_the_same_keys(self):
        self.assertEqual(set(inv.TRANSLATIONS["en"]), set(inv.TRANSLATIONS["tr"]))

    def test_csv_export_streams_sanitized_rows_to_the_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "export.csv"
            write_csv_export(
                destination,
                ("Name", "Path"),
                (("=formula", "/first.pdf"), ("plain", "/second.pdf")),
                ",",
            )

            with destination.open("r", encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(
                    list(csv.reader(stream)),
                    [["Name", "Path"], ["'=formula", "/first.pdf"], ["plain", "/second.pdf"]],
                )

    def test_saved_window_position_must_be_on_screen(self):
        screen = (0, 0, 1920, 1080)
        self.assertTrue(geometry_is_visible("1180x760+100+50", screen))
        self.assertTrue(geometry_is_visible("1180x760+-1500+50", (-1920, 0, 1920, 1080)))
        self.assertFalse(geometry_is_visible("1180x760+-1500+50", screen))
        self.assertFalse(geometry_is_visible("1180x760+100+2000", screen))
        self.assertFalse(geometry_is_visible("3000x760+0+0", screen))
        self.assertFalse(geometry_is_visible("not a geometry", screen))

    def test_problem_text_is_one_bounded_line(self):
        self.assertEqual(one_line("Invalid\n  xref   table"), "Invalid xref table")
        self.assertEqual(len(one_line("x" * 500)), 300)


class PortableModeTest(unittest.TestCase):
    def test_data_lives_next_to_the_script(self):
        self.assertEqual(inv.app_data_dir(), Path(inv.__file__).resolve().parent / "pdf_inventory_data")

    def test_data_lives_next_to_a_packaged_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "PDF Inventory.exe"
            with mock.patch.object(inv.sys, "frozen", True, create=True), \
                    mock.patch.object(inv.sys, "executable", str(executable)):
                self.assertEqual(inv.program_dir(), executable.resolve().parent)
                self.assertEqual(inv.app_data_dir(), executable.resolve().parent / "pdf_inventory_data")

    def test_data_lives_next_to_a_macos_app_bundle_not_inside_it(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "PDF Inventory.app" / "Contents" / "MacOS" / "PDF Inventory"
            executable.parent.mkdir(parents=True)
            executable.touch()
            with mock.patch.object(inv.sys, "frozen", True, create=True), \
                    mock.patch.object(inv.sys, "platform", "darwin"), \
                    mock.patch.object(inv.sys, "executable", str(executable)):
                self.assertEqual(inv.program_dir(), Path(directory).resolve())

    def test_version_is_mvp_1_0_1(self):
        self.assertEqual(inv.APP_VERSION, "MVP 1.0.1")
        for lang in ("en", "tr"):
            self.assertIn("{version}", inv.TRANSLATIONS[lang]["about_version"])

    def test_settings_reports_and_log_share_the_portable_folder(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(inv, "program_dir", lambda: Path(directory)):
            data = Path(directory) / "pdf_inventory_data"
            self.assertEqual(inv.PDFInventoryApp._settings_path(), data / "settings.json")
            self.assertEqual(inv.log_file_path(), data / "pdf_inventory.log")


class InspectionTest(unittest.TestCase):
    @unittest.skipUnless(inv.PYPDF_AVAILABLE, "pypdf is not installed")
    def test_page_count_and_corruption_reason(self):
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / "two pages.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.add_blank_page(width=200, height=200)
            with good.open("wb") as stream:
                writer.write(stream)
            broken = Path(directory) / "broken.pdf"
            broken.write_bytes(b"not a pdf at all")

            self.assertEqual((inspect_pdf(good)["page_state"], inspect_pdf(good)["pages"]), ("ok", 2))
            record = inspect_pdf(broken)
            self.assertEqual(record["page_state"], "corrupt")
            self.assertTrue(record["error"])

    @unittest.skipIf(inv.PYPDF_AVAILABLE, "pypdf is installed")
    def test_pages_are_unavailable_without_pypdf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.pdf"
            path.write_bytes(b"%PDF-1.4")
            self.assertEqual(inspect_pdf(path)["page_state"], "unavailable")


class BoundedMapTest(unittest.TestCase):
    def test_a_stuck_task_times_out_and_the_rest_still_finish(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def work(item):
            if item == "stuck":
                release.wait(30)
            return item.upper()

        results = {}
        started = time.monotonic()
        completed = bounded_map(work, ["stuck"] + [f"f{i}" for i in range(20)], threading.Event(),
                                lambda item, result, error: results.__setitem__(item, error or result),
                                timeout=0.3)

        self.assertTrue(completed)
        self.assertLess(time.monotonic() - started, 10)
        self.assertIsInstance(results.pop("stuck"), TimeoutError)
        self.assertEqual(results, {f"f{i}": f"F{i}" for i in range(20)})

    def test_cancel_returns_without_waiting_for_running_tasks(self):
        release = threading.Event()
        self.addCleanup(release.set)
        cancel = threading.Event()

        def work(item):
            cancel.set()
            release.wait(30)

        started = time.monotonic()
        self.assertFalse(bounded_map(work, range(3), cancel, lambda *_args: None))
        self.assertLess(time.monotonic() - started, 5)


class ScanCorrectnessTest(unittest.TestCase):
    def test_system_folder_names_are_skipped_only_below_a_drive_root(self):
        self.assertEqual(skip_reason(PureWindowsPath(r"C:\Windows")), "system")
        self.assertEqual(skip_reason(PureWindowsPath(r"\\server\share\Program Files")), "system")
        self.assertEqual(skip_reason(PureWindowsPath(r"D:\Books\$RECYCLE.BIN")), "system")
        self.assertIsNone(skip_reason(PureWindowsPath(r"D:\Books\Windows")))

    def test_library_folders_named_like_system_folders_are_scanned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder, name in (("Windows", "Windows Internals.pdf"), ("Linux", "Linux Kernel.pdf"),
                                 ("$RECYCLE.BIN", "deleted.pdf")):
                (root / "books" / folder).mkdir(parents=True)
                (root / "books" / folder / name).write_bytes(b"%PDF-1.4")

            pdfs, skipped = discover(root)

            self.assertEqual(sorted(path.name for path in pdfs), ["Linux Kernel.pdf", "Windows Internals.pdf"])
            self.assertEqual(skipped, [(str(root / "books" / "$RECYCLE.BIN"), "system")])

    @unittest.skipUnless(os.name == "nt", "junctions are a Windows feature")
    def test_junctions_are_listed_as_skipped_instead_of_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            books = root / "books"
            books.mkdir()
            (books / "a.pdf").write_bytes(b"%PDF-1.4")
            make_junction(books / "loop", root)
            make_junction(root / "mirror", books)

            pdfs, skipped = discover(root)

            self.assertEqual(pdfs, [books / "a.pdf"])
            self.assertEqual(sorted(Path(path).name for path, reason in skipped if reason == "link"),
                             ["loop", "mirror"])

    @unittest.skipUnless(os.name == "nt", "junctions are a Windows feature")
    def test_junction_detection_works_without_is_junction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "real").mkdir()
            make_junction(root / "link", root / "real")

            with os.scandir(root) as entries:
                by_name = {entry.name: EntryWithoutJunctionCheck(entry) for entry in entries}

            self.assertTrue(is_link_or_junction(by_name["link"]))
            self.assertFalse(is_link_or_junction(by_name["real"]))

    @unittest.skipUnless(os.name == "nt", "junctions are a Windows feature")
    def test_scan_does_not_report_a_junction_copy_as_a_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "books").mkdir()
            (root / "books" / "a.pdf").write_bytes(b"%PDF-1.4 single copy")
            make_junction(root / "books" / "loop", root)

            events = run_scan(root)

            self.assertEqual([payload["name"] for kind, payload in events if kind == "file"], ["a.pdf"])
            self.assertNotIn(True, final_duplicates(events)["states"].values())
            done = next(payload for kind, payload in events if kind == "done")
            self.assertEqual(done["skipped_folders"], [(str(root / "books" / "loop"), "link")])

    def test_hard_links_are_one_file_not_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "a.pdf"
            original.write_bytes(b"%PDF-1.4 same bytes")
            os.link(original, root / "b.pdf")

            states = final_duplicates(run_scan(root))["states"]

            self.assertEqual({Path(path).name: state for path, state in states.items()},
                             {"a.pdf": False, "b.pdf": False})

    def test_hard_link_of_a_duplicated_file_is_also_a_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "a.pdf"
            original.write_bytes(b"%PDF-1.4 same bytes")
            os.link(original, root / "b.pdf")
            (root / "c.pdf").write_bytes(b"%PDF-1.4 same bytes")

            duplicates = final_duplicates(run_scan(root))

            self.assertEqual({Path(path).name: state for path, state in duplicates["states"].items()},
                             {"a.pdf": True, "b.pdf": True, "c.pdf": True})
            self.assertEqual(set(duplicates["groups"].values()), {1})

    def test_duplicate_groups_are_numbered_by_first_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in (("b1.pdf", b"B" * 50), ("a1.pdf", b"A" * 50), ("b2.pdf", b"B" * 50),
                                  ("a2.pdf", b"A" * 50), ("unique.pdf", b"U" * 50)):
                (root / name).write_bytes(content)

            groups = final_duplicates(run_scan(root))["groups"]

            self.assertEqual({Path(path).name: group for path, group in groups.items()},
                             {"a1.pdf": 1, "a2.pdf": 1, "b1.pdf": 2, "b2.pdf": 2})

    def test_a_pdf_that_hangs_the_parser_is_reported_and_the_scan_finishes(self):
        release = threading.Event()
        self.addCleanup(release.set)
        real_inspect = inv.inspect_pdf

        def inspect(path):
            if path.name == "slow.pdf":
                release.wait(30)
            return real_inspect(path)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "slow.pdf").write_bytes(b"%PDF-1.4 slow")
            (root / "fast.pdf").write_bytes(b"%PDF-1.4 fast")

            with mock.patch.object(inv, "inspect_pdf", inspect), mock.patch.object(inv, "INSPECT_TIMEOUT_SECONDS", 0.3):
                events = run_scan(root)

            slow = final_records(events)["slow.pdf"]
            self.assertEqual(slow["page_state"], "unreadable")
            self.assertIn("Timed out", slow["error"])
            self.assertEqual(slow["size_bytes"], len(b"%PDF-1.4 slow"))
            self.assertIn("fast.pdf", final_records(events))
            self.assertEqual(events[-1][0], "done")


class FilenameCleanerTest(unittest.TestCase):
    def test_removes_only_confirmed_terminal_markers(self):
        self.assertEqual(cleaned_pdf_name("Book (Z-Library).pdf"), ("Book.pdf", "Z-Library"))
        self.assertEqual(
            cleaned_pdf_name("Book (z-library.sk, 1lib.sk, z-lib.sk).PDF"),
            ("Book.PDF", "z-library.sk, 1lib.sk, z-lib.sk"),
        )
        self.assertIsNone(cleaned_pdf_name("Book (Z-Library)_compressed.pdf"))
        self.assertIsNone(cleaned_pdf_name("Book (Z-Library).epub"))
        self.assertIsNone(cleaned_pdf_name("(Z-Library).pdf"))

    def test_collision_is_skipped_without_overwriting_the_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tagged = root / "Book (Z-Library).pdf"
            cleaned = root / "Book.pdf"
            tagged.write_bytes(b"tagged")
            cleaned.write_bytes(b"existing")

            outcomes = apply_renames(plan_renames([tagged]))

            self.assertEqual(outcomes[0].status, "collision")
            self.assertTrue(tagged.exists())
            self.assertEqual(cleaned.read_bytes(), b"existing")

    def test_two_files_cleaning_to_the_same_name_are_both_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "Book (Z-Library).pdf"
            second = root / "Book (z-library.sk, 1lib.sk, z-lib.sk).pdf"
            first.write_bytes(b"1")
            second.write_bytes(b"2")

            self.assertEqual([plan.status for plan in plan_renames([first, second])], ["collision", "collision"])

    def test_preview_reflects_missing_sources_and_taken_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "Gone (Z-Library).pdf"
            taken = root / "Taken (Z-Library).pdf"
            taken.write_bytes(b"x")
            (root / "Taken.pdf").write_bytes(b"y")

            statuses = [plan.status for plan in preflight_renames(plan_renames([missing, taken]))]

            self.assertEqual(statuses, ["skipped", "collision"])

    def test_rename_preserves_pdf_bytes_and_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Book (Z-Library).PDF"
            source.write_bytes(b"unchanged PDF bytes")

            outcomes = apply_renames(plan_renames([source]))
            destination = root / "Book.PDF"

            self.assertEqual(outcomes[0].status, "renamed")
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), b"unchanged PDF bytes")

    def test_report_guided_undo_restores_the_original_filename_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Book (Z-Library).pdf"
            report = root / "reports" / "rename-report.csv"
            source.write_bytes(b"unchanged PDF bytes")

            renamed, error = run_renames(plan_renames([source]), report)
            undo_plans, warnings = load_undo_plans(report)
            restored = apply_renames(undo_plans)

            self.assertIsNone(error)
            self.assertEqual(renamed[0].status, "renamed")
            self.assertEqual(warnings, [])
            self.assertEqual(restored[0].status, "renamed")
            self.assertEqual(source.read_bytes(), b"unchanged PDF bytes")

    def test_reports_from_the_former_command_line_cleaner_still_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Book.pdf").write_bytes(b"bytes")
            report = root / "pdf_filename_cleaner_20261101_151258.csv"
            with report.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\r\n")
                writer.writerow(("Status", "Marker", "Source", "Destination", "Detail"))
                writer.writerow(("renamed", "Z-Library", root / "Book (Z-Library).pdf", root / "Book.pdf",
                                 "Renamed safely"))

            restored = apply_renames(load_undo_plans(report)[0])

            self.assertEqual(restored[0].status, "renamed")
            self.assertTrue((root / "Book (Z-Library).pdf").exists())

    def test_undo_ignores_report_rows_that_are_not_tool_created_renames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "untrusted-report.csv"
            write_rename_report(report, [RenamePlan(root / "unrelated.pdf", root / "other.pdf", "", "renamed", "")])

            plans, warnings = load_undo_plans(report)

            self.assertEqual(plans, [])
            self.assertEqual(warnings, ["Ignored invalid report row 2."])

    def test_nothing_is_renamed_when_the_report_cannot_be_created(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Book (Z-Library).pdf"
            source.write_bytes(b"bytes")
            (root / "not-a-folder").write_text("file", encoding="utf-8")

            with self.assertRaises(OSError):
                run_renames(plan_renames([source]), root / "not-a-folder" / "report.csv")

            self.assertTrue(source.exists())

    def test_a_crash_mid_run_leaves_completed_renames_in_the_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "A (Z-Library).pdf"
            second = root / "B (Z-Library).pdf"
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            report = root / "report.csv"
            real_move = inv._move_without_overwrite

            def crash_on_second(source, destination):
                if source == second:
                    raise KeyboardInterrupt
                real_move(source, destination)

            with mock.patch.object(inv, "_move_without_overwrite", crash_on_second), \
                    self.assertRaises(KeyboardInterrupt):
                run_renames(plan_renames([first, second]), report)

            undo_plans, warnings = load_undo_plans(report)
            self.assertEqual(warnings, [])
            self.assertEqual([plan.destination for plan in undo_plans], [first])

    def test_renames_are_logged_when_the_final_report_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Book (Z-Library).pdf"
            source.write_bytes(b"bytes")
            calls = []

            def flaky_report(destination, plans):
                calls.append(destination)
                if len(calls) == 2:
                    raise OSError("disk full")
                write_rename_report(destination, plans)

            with mock.patch.object(inv, "write_rename_report", flaky_report), \
                    self.assertLogs(level="ERROR") as logs:
                outcomes, error = run_renames(plan_renames([source]), root / "report.csv")

            self.assertEqual(outcomes[0].status, "renamed")
            self.assertIsInstance(error, OSError)
            self.assertIn("Book (Z-Library).pdf", logs.output[0])


class SmokeTestFlagTest(unittest.TestCase):
    """The release workflow launches each built program with --smoke-test and checks the exit code."""

    def setUp(self):
        self.data_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.data_dir, ignore_errors=True))
        for patcher in (mock.patch.object(inv, "app_data_dir", lambda: self.data_dir),
                        mock.patch.object(inv, "SMOKE_TEST_MS", 50)):
            patcher.start()
            self.addCleanup(patcher.stop)
        try:
            tk.Tk().destroy()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")

    def test_a_healthy_start_exits_with_zero(self):
        self.assertEqual(inv.run_smoke_test(require_pdf_library=False), 0)

    def test_a_missing_pdf_library_is_reported_only_when_required(self):
        with mock.patch.object(inv, "PYPDF_AVAILABLE", False):
            self.assertEqual(inv.run_smoke_test(require_pdf_library=False), 0)
            self.assertEqual(inv.run_smoke_test(require_pdf_library=True), inv.EXIT_PDF_LIBRARY_MISSING)

    def test_a_crash_while_starting_exits_with_failure(self):
        with mock.patch.object(inv, "PDFInventoryApp", side_effect=RuntimeError("boom")),                 self.assertLogs(level="ERROR"):
            self.assertEqual(inv.run_smoke_test(require_pdf_library=False), inv.EXIT_SMOKE_FAILED)

    def test_main_passes_the_result_to_the_exit_code(self):
        with mock.patch.object(inv.os, "_exit", side_effect=SystemExit) as leave,                 self.assertRaises(SystemExit):
            inv.main(["--smoke-test"])
        leave.assert_called_once_with(0)


class AppTestCase(unittest.TestCase):
    """Drive a hidden application window with settings and reports in a temporary folder."""

    def setUp(self):
        self.data_dir = Path(tempfile.mkdtemp())
        self.library = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.data_dir, ignore_errors=True))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.library, ignore_errors=True))
        patcher = mock.patch.object(inv, "app_data_dir", lambda: self.data_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")
        self.root.withdraw()
        self.addCleanup(destroy_root, self.root)
        self.app = inv.PDFInventoryApp(self.root)
        self.app.current_lang = "en"
        self.app._update_language()

    def scan(self) -> None:
        self.app.target_directory = str(self.library)
        self.app._start_scan()
        self.app._scan_thread.join(30)
        while self.app.is_scanning or not self.app._queue.empty():
            self.app._poll_worker_queue()

    def table_names(self) -> list:
        return [self.app.tree.set(iid, "name") for iid in self.app.tree.get_children()]


class AppTest(AppTestCase):
    def test_clean_filenames_then_undo_from_the_tools_menu(self):
        nested = self.library / "nested"
        nested.mkdir()
        (self.library / "Top (Z-Library).pdf").write_bytes(b"top")
        (nested / "Deep (z-library.sk, 1lib.sk, z-lib.sk).pdf").write_bytes(b"deep")
        (self.library / "Plain.pdf").write_bytes(b"plain")
        self.scan()

        self.app._open_filename_cleaner()
        dialog = self.app._rename_dialog
        self.assertIsNotNone(dialog)
        plans = preflight_renames(plan_renames(Path(path) for path in self.app.records))
        with mock.patch.object(inv.messagebox, "showinfo") as shown:
            self.app._run_rename_plans(plans, "clean", dialog)

        self.assertIsNone(self.app._rename_dialog)
        self.assertEqual(sorted(path.name for path in self.library.rglob("*.pdf")),
                         ["Deep.pdf", "Plain.pdf", "Top.pdf"])
        self.assertEqual(sorted(self.table_names()), ["Deep.pdf", "Plain.pdf", "Top.pdf"])
        self.assertIn("Renamed 2 of 2", shown.call_args.args[1])
        reports = list((self.data_dir / "rename_reports").glob("pdf_filename_cleaner_*.csv"))
        self.assertEqual(len(reports), 1)

        with mock.patch.object(inv.filedialog, "askopenfilename", return_value=str(reports[0])):
            self.app._open_cleanup_undo()
        undo_plans = preflight_renames(load_undo_plans(reports[0])[0])
        with mock.patch.object(inv.messagebox, "showinfo"):
            self.app._run_rename_plans(undo_plans, "undo", self.app._rename_dialog)

        self.assertEqual(sorted(path.name for path in self.library.rglob("*.pdf")),
                         ["Deep (z-library.sk, 1lib.sk, z-lib.sk).pdf", "Plain.pdf", "Top (Z-Library).pdf"])
        self.assertIn("Top (Z-Library).pdf", self.table_names())

    def test_cleaner_works_on_visible_rows_only(self):
        (self.library / "Keep (Z-Library).pdf").write_bytes(b"1")
        (self.library / "Clean (Z-Library).pdf").write_bytes(b"2")
        self.scan()
        self.app.search_var.set("clean")
        self.app._apply_search()

        self.app._open_filename_cleaner()
        preview = self.app._rename_dialog.winfo_children()[0].winfo_children()
        tree = next(widget for frame in preview for widget in frame.winfo_children()
                    if isinstance(widget, inv.ttk.Treeview))

        self.assertEqual([tree.set(iid, "current") for iid in tree.get_children()], ["Clean (Z-Library).pdf"])

    def test_shortcuts_are_ignored_while_the_rename_dialog_is_open(self):
        (self.library / "Book (Z-Library).pdf").write_bytes(b"1")
        self.scan()
        self.app._open_filename_cleaner()

        with mock.patch.object(self.app, "_start_scan") as start:
            self.app._shortcut_handlers["<Control-r>"](None)
            start.assert_not_called()
            self.app._close_rename_dialog(self.app._rename_dialog)
            self.app._shortcut_handlers["<Control-R>"](None)
            start.assert_called_once()

    def test_shortcuts_work_with_shift_and_caps_lock(self):
        for sequence in ("<Control-f>", "<Control-F>", "<Control-Shift-C>", "<Control-Shift-c>"):
            self.assertTrue(self.root.bind_all(sequence), sequence)

    def test_idle_ticks_do_not_refilter_the_table(self):
        (self.library / "a.pdf").write_bytes(b"1")
        self.scan()
        self.app._sort_by("name")
        self.app.search_var.set("a")
        self.app._apply_search()

        with mock.patch.object(self.app, "_filtered_records", wraps=self.app._filtered_records) as filtered:
            for _ in range(5):
                self.app._poll_worker_queue()

        filtered.assert_not_called()
        self.assertIn("1 shown", self.app.count_label.cget("text"))

    def test_row_stripes_stay_alternating_after_updates(self):
        for index in range(6):
            (self.library / f"{index}.pdf").write_bytes(bytes([index]) * (index + 1))
        self.scan()
        rows = self.app.tree.get_children()
        for path in list(self.app.records)[:5]:
            self.app._mark_path_dirty(path)
        self.app._refresh_table()

        self.assertEqual([self.app.tree.item(iid, "tags")[0] for iid in rows],
                         ["even", "odd", "even", "odd", "even", "odd"])

    def test_sorted_view_adds_scan_rows_at_most_once_per_interval(self):
        (self.library / "a.pdf").write_bytes(b"1")
        self.scan()
        self.app._sort_by("name")
        self.app.is_scanning = True
        self.app._last_full_refresh = time.monotonic()
        new_path = str(self.library / "b.pdf")
        self.app._store_record({**next(iter(self.app.records.values())), "path": new_path, "name": "b.pdf"})

        self.app._refresh_table(throttle=True)
        self.assertEqual(self.table_names(), ["a.pdf"])
        self.assertTrue(self.app._refresh_pending)

        self.app._last_full_refresh = 0.0
        self.app._refresh_table(throttle=True)
        self.assertEqual(self.table_names(), ["a.pdf", "b.pdf"])
        self.app.is_scanning = False

    def test_a_new_scan_removes_rows_hidden_by_the_previous_search(self):
        (self.library / "keep.pdf").write_bytes(b"1")
        (self.library / "gone.pdf").write_bytes(b"22")
        self.scan()
        self.app.search_var.set("keep")
        self.app._apply_search()
        (self.library / "gone.pdf").unlink()

        self.scan()

        self.assertEqual(self.table_names(), ["keep.pdf"])
        self.assertEqual(len(self.app._path_by_iid), 1)

    def test_duplicates_show_their_group_and_reclaimable_space(self):
        (self.library / "a.pdf").write_bytes(b"same" * 256)
        (self.library / "b.pdf").write_bytes(b"same" * 256)
        (self.library / "c.pdf").write_bytes(b"other")
        self.scan()

        duplicate_cells = {self.app.tree.set(iid, "name"): self.app.tree.set(iid, "duplicate")
                           for iid in self.app.tree.get_children()}
        self.assertEqual(duplicate_cells, {"a.pdf": "Yes · group 1", "b.pdf": "Yes · group 1", "c.pdf": "No"})
        self.assertIn("2 duplicate files in 1 groups (1.0 KB reclaimable)", self.app.lbl_status.cget("text"))

    def test_export_adds_problem_and_exact_size_and_waits_for_the_scan(self):
        (self.library / "a.pdf").write_bytes(b"12345")
        self.scan()
        destination = self.library / "export.csv"

        self.app.is_scanning = True
        with mock.patch.object(inv.filedialog, "asksaveasfilename") as ask:
            self.app._export_csv()
        ask.assert_not_called()
        self.app.is_scanning = False

        with mock.patch.object(inv.filedialog, "asksaveasfilename", return_value=str(destination)):
            self.app._export_csv()
        with destination.open(encoding="utf-8-sig", newline="") as stream:
            header, row = list(csv.reader(stream, delimiter=resolve_csv_delimiter("auto", "en")))
        self.assertIn("Problem", header)
        self.assertEqual(header[-1], "Size (bytes)")
        self.assertEqual(row[-1], "5")

    def test_each_launch_starts_in_the_program_folder_not_the_last_one(self):
        settings = self.data_dir / "settings.json"
        settings.write_text(json.dumps({"target_directory": str(self.library)}), encoding="utf-8")
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(destroy_root, root)
        app = inv.PDFInventoryApp(root)

        self.assertEqual(app.target_directory, str(Path(inv.__file__).resolve().parent))
        with mock.patch.object(inv.filedialog, "askdirectory", return_value=str(self.library)):
            app._select_folder()
        self.assertEqual(app.target_directory, os.path.normpath(str(self.library)))
        app._save_settings()
        self.assertNotIn("target_directory", json.loads(settings.read_text(encoding="utf-8")))

    def test_resource_menu_starts_at_medium_and_reaches_the_scanner(self):
        self.assertEqual(self.app.resource_governor.level, "medium")
        self.assertEqual(self.app.resource_level_var.get(), "medium")
        self.assertEqual(self.app.tools_menu.entrycget(3, "label"), "Resource usage")
        self.assertTrue(self.app.resources_menu.entrycget(3, "label").startswith("Medium"))

        with mock.patch.object(inv, "apply_process_priority") as priority:
            self.app.resource_level_var.set("low")
            self.app._on_resource_level_change()
        priority.assert_called_once_with(True)
        self.assertEqual(self.app.resource_governor.level, "low")
        self.assertIn("Resource usage set to Low", self.app.lbl_status.cget("text"))

        (self.library / "a.pdf").write_bytes(b"a")
        with mock.patch.object(inv, "scan_folder", wraps=inv.scan_folder) as scanner:
            self.scan()
        self.assertIs(scanner.call_args.args[3], self.app.resource_governor)
        self.app._save_settings()
        self.assertNotIn("resource_level", json.loads((self.data_dir / "settings.json").read_text(encoding="utf-8")))
        with mock.patch.object(inv, "apply_process_priority"):
            self.app.resource_governor.set_level("medium")

    def test_resource_change_during_a_scan_is_announced_next_to_the_progress(self):
        self.app.is_scanning = True
        self.app._set_status("status_scanning", current=3, total=10)
        with mock.patch.object(inv, "apply_process_priority"):
            self.app.resource_level_var.set("high")
            self.app._on_resource_level_change()
            text = self.app.lbl_status.cget("text")
            self.assertTrue(text.startswith("Inspecting PDFs: 3/10"))
            self.assertIn("Speed increased to High", text)
            self.assertEqual(self.app.resource_governor.level, "high")

            # The notice stays while progress updates arrive.
            self.app._set_status("status_scanning", current=4, total=10)
            self.assertIn("Speed increased to High", self.app.lbl_status.cget("text"))

            self.app.resource_level_var.set("low")
            self.app._on_resource_level_change()
            self.assertIn("Speed lowered to Low", self.app.lbl_status.cget("text"))

            self.app._expire_resource_notice()
            self.assertEqual(self.app.lbl_status.cget("text"), "Inspecting PDFs: 4/10")
            self.app.resource_governor.set_level("medium")
        self.app.is_scanning = False

    def test_tools_are_on_the_main_window_and_follow_the_menu(self):
        self.assertEqual(str(self.app.btn_clean.cget("state")), tk.DISABLED)
        self.assertEqual(str(self.app.btn_undo.cget("state")), tk.NORMAL)
        self.assertTrue(self.app.resource_combo.get().startswith("Medium"))
        self.assertIn("Kerem Aydın", self.app.lbl_credit.cget("text"))

        (self.library / "a.pdf").write_bytes(b"a")
        self.scan()
        self.assertEqual(str(self.app.btn_clean.cget("state")), tk.NORMAL)

        with mock.patch.object(inv, "apply_process_priority"):
            high = next(label for label, level in self.app._resource_labels.items() if level == "high")
            self.app.resource_combo.set(high)
            self.app._on_resource_combo_change()
            self.assertEqual(self.app.resource_governor.level, "high")
            self.assertEqual(self.app.resource_level_var.get(), "high")
            self.app.resource_level_var.set("medium")
            self.app._on_resource_level_change()
        self.assertTrue(self.app.resource_combo.get().startswith("Medium"))

    def test_settings_gear_and_tools_menu_share_language_and_separator(self):
        self.assertEqual(self.app.tools_menu.entrycget(5, "label"), "Language")
        self.assertEqual(self.app.settings_menu.entrycget(1, "label"), "CSV separator")

        self.app.language_var.set("tr")
        self.app._on_language_change()
        self.app.separator_var.set("semicolon")
        self.app._on_separator_change()

        self.assertEqual(self.app.btn_export.cget("text"), "CSV olarak aktar")
        self.assertEqual(self.app.settings_menu.entrycget(0, "label"), "Dil")
        saved = json.loads((self.data_dir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["language"], saved["csv_separator"]), ("tr", "semicolon"))

    def test_empty_hint_and_progress_show_only_while_relevant(self):
        self.root.update_idletasks()
        self.assertTrue(self.app.empty_hint.place_info())
        self.assertIn("Start scan", self.app.empty_hint.cget("text"))
        self.assertFalse(self.app.progress.winfo_manager())

        self.scan()
        self.assertIn("No PDF files", self.app.empty_hint.cget("text"))
        (self.library / "a.pdf").write_bytes(b"a")
        self.scan()

        self.assertFalse(self.app.empty_hint.place_info())
        self.assertFalse(self.app.progress.winfo_manager())

    def test_off_screen_saved_position_is_replaced(self):
        (self.data_dir / "settings.json").write_text('{"geometry": "1180x760+-9000+-9000"}', encoding="utf-8")
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(destroy_root, root)
        inv.PDFInventoryApp(root)
        root.update_idletasks()

        self.assertNotIn("-9000", root.geometry())


if __name__ == "__main__":
    unittest.main()
