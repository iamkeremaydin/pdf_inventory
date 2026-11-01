import unittest

from pdf_inventory import MAX_IN_FLIGHT_PER_WORKER, MAX_SCAN_WORKERS, normalize_search, resolve_csv_delimiter, sanitize_csv_cell


class InventoryHelpersTest(unittest.TestCase):
    def test_scan_concurrency_is_fixed_and_bounded(self):
        self.assertEqual(MAX_SCAN_WORKERS, 4)
        self.assertEqual(MAX_SCAN_WORKERS * MAX_IN_FLIGHT_PER_WORKER, 8)

    def test_search_normalization_handles_turkish_and_diacritics(self):
        self.assertEqual(normalize_search("İstanbul ıŞık café"), "istanbul isik cafe")

    def test_csv_delimiter_respects_locale_and_explicit_choice(self):
        self.assertEqual(resolve_csv_delimiter("auto", "tr"), ";")
        self.assertEqual(resolve_csv_delimiter("tab", "en"), "\t")

    def test_csv_formula_prefix_is_neutralized(self):
        self.assertEqual(sanitize_csv_cell("  =1+1"), "'  =1+1")
        self.assertEqual(sanitize_csv_cell(42), 42)


if __name__ == "__main__":
    unittest.main()
