import csv
import tempfile
import threading
import unittest
from pathlib import Path

from pdf_inventory import (
    MAX_IN_FLIGHT_PER_WORKER,
    MAX_SCAN_WORKERS,
    MAX_UI_QUEUE_EVENTS,
    _full_hash,
    _quick_hash,
    normalize_search,
    resolve_csv_delimiter,
    sanitize_csv_cell,
    write_csv_export,
)


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


if __name__ == "__main__":
    unittest.main()
