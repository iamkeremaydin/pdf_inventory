import csv
import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

from pdf_inventory import (
    MAX_IN_FLIGHT_PER_WORKER,
    MAX_SCAN_WORKERS,
    MAX_UI_QUEUE_EVENTS,
    PDFInventoryApp,
    _full_hash,
    _quick_hash,
    is_link_or_junction,
    normalize_search,
    resolve_csv_delimiter,
    sanitize_csv_cell,
    skip_reason,
    write_csv_export,
)


def make_junction(link: Path, target: Path) -> None:
    import _winapi

    _winapi.CreateJunction(str(target), str(link))


def discover(root: Path):
    return PDFInventoryApp._discover_pdfs(root, threading.Event(), lambda *_args: None)


def run_scan(root: Path) -> list:
    """Run the scan pipeline without Tk and return the events it sends to the UI."""
    events: queue.Queue = queue.Queue()
    worker = SimpleNamespace(_discover_pdfs=PDFInventoryApp._discover_pdfs,
                             _cancel_event=threading.Event(), _queue=events)
    PDFInventoryApp._scan_worker(worker, root)
    collected = []
    while not events.empty():
        collected.append(events.get_nowait())
    return collected


def final_duplicate_states(events: list) -> dict:
    return next(payload for kind, payload in events if kind == "duplicates")


class EntryWithoutJunctionCheck:
    """Mimic os.DirEntry on Python 3.10 and 3.11, which have no is_junction()."""

    def __init__(self, entry):
        self._entry = entry

    def is_symlink(self):
        return self._entry.is_symlink()

    def stat(self, *, follow_symlinks=True):
        return self._entry.stat(follow_symlinks=follow_symlinks)


class InventoryHelpersTest(unittest.TestCase):
    def test_scan_concurrency_is_fixed_and_bounded(self):
        self.assertEqual(MAX_SCAN_WORKERS, 4)
        self.assertEqual(MAX_SCAN_WORKERS * MAX_IN_FLIGHT_PER_WORKER, 8)
        self.assertEqual(MAX_UI_QUEUE_EVENTS, 512)

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

    def test_invalid_folder_message_is_translated(self):
        from pdf_inventory import TRANSLATIONS

        for language in ("en", "tr"):
            self.assertTrue(TRANSLATIONS[language]["msg_invalid_folder"])

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
            self.assertNotIn(True, final_duplicate_states(events).values())
            done = next(payload for kind, payload in events if kind == "done")
            self.assertEqual(done["skipped_folders"], [(str(root / "books" / "loop"), "link")])

    def test_hard_links_are_one_file_not_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "a.pdf"
            original.write_bytes(b"%PDF-1.4 same bytes")
            os.link(original, root / "b.pdf")

            states = final_duplicate_states(run_scan(root))

            self.assertFalse(states.get(str(original), False))
            self.assertFalse(states[str(root / "b.pdf")])

    def test_hard_link_of_a_duplicated_file_is_also_a_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "a.pdf"
            original.write_bytes(b"%PDF-1.4 same bytes")
            os.link(original, root / "b.pdf")
            (root / "c.pdf").write_bytes(b"%PDF-1.4 same bytes")

            states = final_duplicate_states(run_scan(root))

            self.assertEqual({Path(path).name: state for path, state in states.items()},
                             {"a.pdf": True, "b.pdf": True, "c.pdf": True})


if __name__ == "__main__":
    unittest.main()
