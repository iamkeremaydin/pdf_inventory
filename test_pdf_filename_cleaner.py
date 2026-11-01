import contextlib
import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pdf_filename_cleaner import (
    SCRIPT_DIR,
    apply_renames,
    cleaned_pdf_name,
    load_undo_plans,
    main,
    parse_args,
    plan_renames,
    scan_pdf_files,
    write_report,
)


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

    @unittest.skipUnless(os.name == "nt", "junctions are a Windows feature")
    def test_scan_does_not_follow_a_junction_back_into_the_tree(self):
        import _winapi

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            (nested / "Book (Z-Library).pdf").write_bytes(b"pdf bytes")
            _winapi.CreateJunction(str(root), str(nested / "loop"))

            files, warnings = scan_pdf_files(root)

            self.assertEqual(warnings, [])
            self.assertEqual(files, [nested / "Book (Z-Library).pdf"])

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

    def test_report_guided_undo_restores_the_original_filename_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Book (Z-Library).pdf"
            report = root / "rename-report.csv"
            source.write_bytes(b"unchanged PDF bytes")

            renamed = apply_renames(plan_renames([source]))
            write_report(report, renamed)
            undo_plans, warnings = load_undo_plans(report)
            restored = apply_renames(undo_plans)

            self.assertEqual(warnings, [])
            self.assertEqual(restored[0].status, "renamed")
            self.assertTrue(source.exists())
            self.assertEqual(source.read_bytes(), b"unchanged PDF bytes")

    def test_undo_ignores_report_rows_that_are_not_tool_created_renames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "untrusted-report.csv"
            with report.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(("Status", "Marker", "Source", "Destination", "Detail"))
                writer.writerow(("renamed", "", root / "unrelated.pdf", root / "other.pdf", "Injected"))

            plans, warnings = load_undo_plans(report)

            self.assertEqual(plans, [])
            self.assertEqual(warnings, ["Ignored invalid report row 2."])

    def test_default_folder_is_the_script_folder_not_the_working_directory(self):
        self.assertEqual(parse_args([]).root, SCRIPT_DIR)

    def test_preview_explains_that_nothing_was_renamed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "nested" / "Book (Z-Library).pdf"
            source.parent.mkdir()
            source.write_bytes(b"pdf bytes")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                code = main([str(root)])

            self.assertEqual(code, 0)
            self.assertTrue(source.exists())
            self.assertIn("no files were renamed", output.getvalue())

    def test_double_click_run_asks_for_confirmation_then_renames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "nested" / "Book (Z-Library).pdf"
            source.parent.mkdir()
            source.write_bytes(b"pdf bytes")

            with mock.patch("builtins.input", return_value="RENAME") as prompt, \
                    contextlib.redirect_stdout(io.StringIO()):
                code = main([str(root)], double_clicked=True)

            self.assertEqual(code, 0)
            prompt.assert_called_once()
            self.assertFalse(source.exists())
            self.assertEqual((root / "nested" / "Book.pdf").read_bytes(), b"pdf bytes")
            self.assertEqual(len(list(root.glob("pdf_filename_cleaner_*.csv"))), 1)

    def test_audit_report_keeps_renames_when_the_final_summary_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Book (Z-Library).pdf"
            report = root / "audit.csv"
            source.write_bytes(b"pdf bytes")

            def fail_after_apply(plans, dry_run, *args, **kwargs):
                if not dry_run:
                    raise KeyboardInterrupt

            with mock.patch("pdf_filename_cleaner.print_summary", side_effect=fail_after_apply), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
                main([str(root), "--apply", "--yes", "--report", str(report)])

            undo_plans, warnings = load_undo_plans(report)
            self.assertEqual(warnings, [])
            self.assertEqual([plan.destination for plan in undo_plans], [source])


if __name__ == "__main__":
    unittest.main()
