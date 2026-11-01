import tempfile
import unittest
from pathlib import Path

from pdf_filename_cleaner import apply_renames, cleaned_pdf_name, plan_renames, scan_pdf_files


class PdfFilenameCleanerTest(unittest.TestCase):
    def test_removes_only_confirmed_terminal_markers(self):
        self.assertEqual(cleaned_pdf_name("Book (Z-Library).pdf"), ("Book.pdf", "Z-Library"))
        self.assertEqual(
            cleaned_pdf_name("Book (z-library.sk, 1lib.sk, z-lib.sk).PDF"),
            ("Book.PDF", "z-library.sk, 1lib.sk, z-lib.sk"),
        )
        self.assertIsNone(cleaned_pdf_name("Book (Z-Library)_compressed.pdf"))
        self.assertIsNone(cleaned_pdf_name("Book (Z-Library).epub"))

    def test_scans_subfolders_and_ignores_non_pdfs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            (nested / "Book (Z-Library).pdf").write_bytes(b"pdf bytes")
            (root / "notes.txt").write_text("not a PDF", encoding="utf-8")

            files, warnings = scan_pdf_files(root)

            self.assertEqual(warnings, [])
            self.assertEqual([path.name for path in files], ["Book (Z-Library).pdf"])

    def test_collision_is_skipped_without_overwriting_the_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tagged = root / "Book (Z-Library).pdf"
            cleaned = root / "Book.pdf"
            tagged.write_bytes(b"tagged")
            cleaned.write_bytes(b"existing")

            plans = plan_renames([tagged])
            outcomes = apply_renames(plans)

            self.assertEqual(outcomes[0].status, "collision")
            self.assertTrue(tagged.exists())
            self.assertEqual(cleaned.read_bytes(), b"existing")

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


if __name__ == "__main__":
    unittest.main()
