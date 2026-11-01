#!/usr/bin/env python3
"""PDF Master Suite - responsive PDF inventory for Windows, macOS and Linux."""
from __future__ import annotations

import csv
import hashlib
import json
import locale
import logging
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import unicodedata
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# Keep optional PDF-library diagnostics quiet without suppressing unrelated warnings.
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("PyPDF2").setLevel(logging.ERROR)
try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfReader
        PYPDF_AVAILABLE = True
    except ImportError:
        PdfReader = None  # type: ignore[assignment,misc]
        PYPDF_AVAILABLE = False


TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "title": "PDF Master Suite — Inventory",
        "target_dir": "Target folder",
        "language": "Language",
        "csv_separator": "CSV separator",
        "sep_auto": "Auto",
        "sep_comma": "Comma ( , )",
        "sep_semicolon": "Semicolon ( ; )",
        "sep_tab": "Tab",
        "browse": "Browse…",
        "scan": "Start scan",
        "cancel_scan": "Cancel scan",
        "export": "Export visible rows",
        "search": "Search",
        "search_hint": "Name, folder or path…",
        "clear": "Clear",
        "duplicates_only": "Duplicates only",
        "col_name": "File name",
        "col_folder": "Folder",
        "col_size": "Size",
        "col_pages": "Pages",
        "col_date": "Modified",
        "col_duplicate": "Duplicate",
        "col_path": "Full path",
        "status_ready": "Ready. Select a folder and start a scan.",
        "status_discovering": "Discovering… {files} PDFs found in {folders} folders.",
        "status_scanning": "Inspecting PDFs: {current}/{total}",
        "status_hashing_quick": "Checking duplicate candidates (quick hash): {current}/{total}",
        "status_hashing_full": "Verifying possible duplicates (SHA-256): {current}/{total}",
        "status_done": "Done: {count} PDFs · {duplicates} duplicate files · {corrupt} corrupted · {errors} unreadable · {skipped} folders skipped.",
        "status_cancelled": "Cancelled: {count} PDFs collected · {duplicates} duplicates confirmed.",
        "status_no_pdf": "No PDF files were found in the selected folder.",
        "status_cancelling": "Cancelling… finishing active file operations.",
        "status_exported": "Exported {count} visible rows to {path}",
        "status_scan_error": "Scan failed: {error}",
        "status_missing_library": " Page counts unavailable: install pypdf to inspect PDF pages.",
        "yes": "Yes",
        "no": "No",
        "pending": "Checking…",
        "unknown": "Unknown",
        "page_corrupt": "Corrupted",
        "page_encrypted": "Encrypted",
        "page_unavailable": "Unavailable",
        "page_unreadable": "Unreadable",
        "msg_warning": "Warning",
        "msg_error": "Error",
        "msg_no_data": "There are no visible rows to export.",
        "msg_export_error": "The CSV file could not be saved:\n{error}",
        "msg_folder_error": "The folder could not be opened:\n{error}",
        "msg_file_error": "The file could not be opened:\n{error}",
        "msg_copy_error": "The path could not be copied:\n{error}",
        "msg_invalid_folder": "The selected folder does not exist or cannot be accessed.",
        "open_file": "Open file",
        "open_folder": "Open containing folder",
        "copy_path": "Copy full path",
        "copied": "Path copied to clipboard.",
        "count_label": "{visible} shown / {total} total",
        "filename_prefix": "pdf_inventory",
        "choose_folder": "Select the folder to scan",
        "choose_export": "Export CSV",
        "skipped_button": "Skipped folders ({count})",
        "skipped_title": "Skipped folders",
        "skipped_intro": "These folders were not scanned:",
        "skipped_more": "…and {count} more.",
        "skip_reason_system": "System folder",
        "skip_reason_link": "Link or junction",
        "skip_reason_access": "No access",
    },
    "tr": {
        "title": "PDF Master Suite — Envanter",
        "target_dir": "Hedef klasör",
        "language": "Dil",
        "csv_separator": "CSV ayırıcı",
        "sep_auto": "Otomatik",
        "sep_comma": "Virgül ( , )",
        "sep_semicolon": "Noktalı virgül ( ; )",
        "sep_tab": "Sekme",
        "browse": "Gözat…",
        "scan": "Taramayı başlat",
        "cancel_scan": "Taramayı iptal et",
        "export": "Görünen satırları aktar",
        "search": "Ara",
        "search_hint": "Ad, klasör veya yol…",
        "clear": "Temizle",
        "duplicates_only": "Yalnızca yinelenenler",
        "col_name": "Dosya adı",
        "col_folder": "Klasör",
        "col_size": "Boyut",
        "col_pages": "Sayfa",
        "col_date": "Değiştirilme",
        "col_duplicate": "Yinelenen",
        "col_path": "Tam yol",
        "status_ready": "Hazır. Bir klasör seçip taramayı başlatın.",
        "status_discovering": "Dosyalar aranıyor… {folders} klasörde {files} PDF bulundu.",
        "status_scanning": "PDF'ler inceleniyor: {current}/{total}",
        "status_hashing_quick": "Yinelenen adayları hızlı hash ile kontrol ediliyor: {current}/{total}",
        "status_hashing_full": "Olası kopyalar SHA-256 ile doğrulanıyor: {current}/{total}",
        "status_done": "Tamamlandı: {count} PDF · {duplicates} yinelenen dosya · {corrupt} bozuk · {errors} okunamadı · {skipped} klasör atlandı.",
        "status_cancelled": "İptal edildi: {count} PDF toplandı · {duplicates} yinelenen dosya doğrulandı.",
        "status_no_pdf": "Seçilen klasörde PDF bulunamadı.",
        "status_cancelling": "İptal ediliyor… devam eden dosya işlemleri tamamlanıyor.",
        "status_exported": "{count} görünür satır {path} konumuna aktarıldı.",
        "status_scan_error": "Tarama başarısız: {error}",
        "status_missing_library": " Sayfa sayıları için pypdf kütüphanesini yükleyin.",
        "yes": "Evet",
        "no": "Hayır",
        "pending": "Kontrol ediliyor…",
        "unknown": "Bilinmiyor",
        "page_corrupt": "Bozuk",
        "page_encrypted": "Şifreli",
        "page_unavailable": "Kullanılamıyor",
        "page_unreadable": "Okunamadı",
        "msg_warning": "Uyarı",
        "msg_error": "Hata",
        "msg_no_data": "Dışa aktarılacak görünür satır yok.",
        "msg_export_error": "CSV dosyası kaydedilemedi:\n{error}",
        "msg_folder_error": "Klasör açılamadı:\n{error}",
        "msg_file_error": "Dosya açılamadı:\n{error}",
        "msg_copy_error": "Dosya yolu kopyalanamadı:\n{error}",
        "msg_invalid_folder": "Seçilen klasör mevcut değil veya erişilemiyor.",
        "open_file": "Dosyayı aç",
        "open_folder": "Bulunduğu klasörü aç",
        "copy_path": "Tam yolu kopyala",
        "copied": "Dosya yolu panoya kopyalandı.",
        "count_label": "{visible} gösteriliyor / toplam {total}",
        "filename_prefix": "pdf_envanteri",
        "choose_folder": "Taranacak klasörü seçin",
        "choose_export": "CSV dışa aktar",
        "skipped_button": "Atlanan klasörler ({count})",
        "skipped_title": "Atlanan klasörler",
        "skipped_intro": "Bu klasörler taranmadı:",
        "skipped_more": "…ve {count} klasör daha.",
        "skip_reason_system": "Sistem klasörü",
        "skip_reason_link": "Sembolik bağlantı veya bağlantı noktası",
        "skip_reason_access": "Erişim yok",
    },
}


# Directories that are almost never useful in an inventory scan. The selected
# root itself is still scanned even when its name matches one of these entries.
# Volume bookkeeping folders are skipped wherever they appear.
VOLUME_SKIP_DIR_NAMES = {
    "$recycle.bin", "system volume information", "$winreagent",
    ".spotlight-v100", ".trashes", ".fseventsd", ".documentrevisions-v100",
    ".temporaryitems",
}
# Operating-system folders are skipped only directly below a drive root, so a
# library folder such as Books/Windows is still scanned.
SYSTEM_SKIP_DIR_NAMES = {
    "windows", "program files", "program files (x86)", "programdata", "perflogs",
}
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
PARTIAL_HASH_BLOCK = 64 * 1024
FULL_HASH_CHUNK = 1024 * 1024
# Keep reader and hashing concurrency predictable on machines with many cores.
MAX_SCAN_WORKERS = 4
MAX_IN_FLIGHT_PER_WORKER = 2
# Backpressure prevents a fast scanner from retaining an unbounded number of
# pending UI updates while the main thread renders a large result set.
MAX_UI_QUEUE_EVENTS = 512


def skip_reason(path: Path) -> str | None:
    """Return why a directory below the scan root is skipped, or None to scan it."""
    name = path.name.casefold()
    if name in VOLUME_SKIP_DIR_NAMES:
        return "system"
    if name in SYSTEM_SKIP_DIR_NAMES and path.parent.parent == path.parent:
        return "system"
    return None


def is_link_or_junction(entry: os.DirEntry[str]) -> bool:
    """True for symlinks and Windows junctions, which can loop back into the scanned tree."""
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)  # Python 3.12+
    if is_junction is not None:
        return bool(is_junction())
    return getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0) == IO_REPARSE_TAG_MOUNT_POINT


def normalize_search(value: str) -> str:
    """Case/diacritic-insensitive matching, including Turkish dotted/dotless I."""
    value = value.casefold().replace("ı", "i")
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def resolve_csv_delimiter(setting: str, language: str = "en", decimal_point: str | None = None) -> str:
    """Resolve an explicit CSV delimiter or choose a locale-friendly default."""
    choices = {"comma": ",", "semicolon": ";", "tab": "\t"}
    if setting in choices:
        return choices[setting]
    if decimal_point is None:
        try:
            decimal_point = locale.localeconv().get("decimal_point", ".")
        except Exception:
            decimal_point = "."
    return ";" if decimal_point == "," or language == "tr" else ","


def sanitize_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet formula execution while preserving non-string types."""
    if not isinstance(value, str):
        return value
    stripped = value.lstrip(" \t\r\n")
    if stripped.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_csv_export(destination: Path, headers: Sequence[Any], rows: Iterable[Sequence[Any]],
                     delimiter: str) -> None:
    """Write an export atomically without materializing all rows in memory."""
    temp_name: str | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", errors="replace", newline="", delete=False,
                                         dir=destination.parent, suffix=".tmp") as stream:
            temp_name = stream.name
            writer = csv.writer(stream, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
            writer.writerow([sanitize_csv_cell(item) for item in headers])
            for row in rows:
                writer.writerow([sanitize_csv_cell(item) for item in row])
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
        temp_name = None
    except (OSError, csv.Error, UnicodeError):
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise


def _quick_hash(path: Path, expected_size: int, expected_mtime_ns: int | None = None) -> str | None:
    """Hash file size plus its first/last blocks; only a candidate pre-filter."""
    digest = hashlib.blake2b(digest_size=20)
    digest.update(str(expected_size).encode("ascii"))
    with path.open("rb") as stream:
        if expected_size <= PARTIAL_HASH_BLOCK * 2:
            digest.update(stream.read())
        else:
            digest.update(stream.read(PARTIAL_HASH_BLOCK))
            stream.seek(max(PARTIAL_HASH_BLOCK, expected_size - PARTIAL_HASH_BLOCK))
            digest.update(stream.read(PARTIAL_HASH_BLOCK))
    after = path.stat()
    if after.st_size != expected_size:
        return None
    if expected_mtime_ns is not None and after.st_mtime_ns != expected_mtime_ns:
        return None
    return digest.hexdigest()


def _full_hash(path: Path, expected_size: int, expected_mtime_ns: int | None = None,
               cancel_event: threading.Event | None = None) -> str | None:
    """Compute SHA-256 in bounded chunks and reject files changed mid-scan."""
    if cancel_event is not None and cancel_event.is_set():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                return None
            chunk = stream.read(FULL_HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    after = path.stat()
    if after.st_size != expected_size:
        return None
    if expected_mtime_ns is not None and after.st_mtime_ns != expected_mtime_ns:
        return None
    return digest.hexdigest()


def inspect_pdf(path: Path) -> dict[str, Any]:
    """Inspect one PDF without touching Tk; safe to call from a worker thread."""
    record: dict[str, Any] = {
        "path": str(path), "name": path.name, "folder": path.parent.name,
        "size_bytes": None, "mtime": None, "mtime_ns": None, "pages": None,
        "page_state": "unavailable" if not PYPDF_AVAILABLE else "pending",
        "duplicate": False, "quick_hash": None, "error": None, "file_id": None,
    }
    try:
        stat = path.stat()
        record.update(size_bytes=stat.st_size, mtime=stat.st_mtime, mtime_ns=stat.st_mtime_ns,
                      file_id=(stat.st_dev, stat.st_ino) if stat.st_ino else None)
    except OSError as exc:
        record.update(page_state="unreadable", error=str(exc))
        return record

    if not PYPDF_AVAILABLE:
        return record

    try:
        with path.open("rb") as stream:
            reader = PdfReader(stream, strict=False)  # type: ignore[misc,operator]
            if reader.is_encrypted:
                try:
                    decrypted = reader.decrypt("")
                except Exception:
                    decrypted = 0
                if not decrypted:
                    record["page_state"] = "encrypted"
                    return record
            record["pages"] = len(reader.pages)
            record["page_state"] = "ok"
    except (PermissionError, FileNotFoundError, IsADirectoryError, OSError) as exc:
        record.update(page_state="unreadable", error=str(exc))
    except Exception as exc:
        record.update(page_state="corrupt", error=str(exc))
    return record


class PDFInventoryApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings_path = self._settings_path()
        self.settings = self._load_settings()
        saved_lang = self.settings.get("language")
        self.current_lang = saved_lang if saved_lang in TRANSLATIONS else self._get_system_language()
        saved_dir = self.settings.get("target_directory")
        self.target_directory = str(Path(saved_dir).expanduser()) if saved_dir and Path(saved_dir).expanduser().is_dir() else self._get_base_directory()
        self.csv_separator = self.settings.get("csv_separator", "auto")
        if self.csv_separator not in {"auto", "comma", "semicolon", "tab"}:
            self.csv_separator = "auto"
        self.last_export_dir = self.settings.get("last_export_dir", self.target_directory)
        self.records: dict[str, dict[str, Any]] = {}
        self._insertion_order: list[str] = []
        self._iid_by_path: dict[str, str] = {}
        self._path_by_iid: dict[str, str] = {}
        self._pending_render_paths: list[str] = []
        self._pending_render_set: set[str] = set()
        self._table_mode: tuple[str, str | None, bool, bool] | None = None
        self._visible_paths: list[str] = []
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=MAX_UI_QUEUE_EVENTS)
        self._cancel_event = threading.Event()
        self._scan_thread: threading.Thread | None = None
        self.is_scanning = False
        self._closing = False
        self._search_after_id: str | None = None
        self._last_status: tuple[str, dict[str, Any]] = ("status_ready", {})
        self._scan_progress = 0
        self._scan_total = 0
        self._skipped_dirs = 0
        self._skipped_folders: list[tuple[str, str]] = []
        self._sort_column: str | None = None
        self._sort_reverse = False
        self.duplicates_only_var = tk.BooleanVar(value=False)
        self._ui_scale = 1.0

        self._setup_window()
        self._setup_styles()
        self._setup_ui()
        self._update_language()
        self._set_status("status_ready")
        if not PYPDF_AVAILABLE:
            self._append_library_warning()
        self.root.after(100, self._poll_worker_queue)

    # ---------- Paths and settings ----------
    @staticmethod
    def _settings_path() -> Path:
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "PDFMasterSuite" / "settings.json"

    @staticmethod
    def _load_settings() -> dict[str, Any]:
        path = PDFInventoryApp._settings_path()
        try:
            with path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_settings(self) -> None:
        payload = {
            "language": self.current_lang,
            "target_directory": self.target_directory,
            "csv_separator": self.csv_separator,
            "last_export_dir": self.last_export_dir,
            "geometry": self.root.geometry(),
        }
        temp_name: str | None = None
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False,
                                             dir=self.settings_path.parent, suffix=".tmp") as stream:
                temp_name = stream.name
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.settings_path)
            if os.name != "nt":
                try:
                    self.settings_path.chmod(0o600)
                except OSError:
                    pass
        except OSError:
            logging.exception("Could not save application settings")
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

    @staticmethod
    def _get_base_directory() -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def _get_system_language() -> str:
        try:
            if sys.platform == "win32":
                lang_id = ctypes_lang_id()
                if (lang_id & 0x3FF) == 0x1F:
                    return "tr"
            sys_loc = locale.getlocale()[0]
            if sys_loc and sys_loc.lower().startswith("tr"):
                return "tr"
        except Exception:
            pass
        return "en"

    def _t(self, key: str, **kwargs: Any) -> str:
        template = TRANSLATIONS[self.current_lang].get(key, TRANSLATIONS["en"].get(key, key))
        try:
            return template.format(**kwargs) if kwargs else template
        except (KeyError, ValueError):
            return template

    def _px(self, value: int | float) -> int:
        """Convert design pixels using the detected display scale."""
        return max(1, round(value * self._ui_scale))

    # ---------- Window, style and interface ----------
    def _setup_window(self) -> None:
        self.root.update_idletasks()
        try:
            self._ui_scale = max(0.85, min(2.0, self.root.winfo_fpixels("1i") / 96.0))
        except tk.TclError:
            self._ui_scale = 1.0
        width, height = self._px(1180), self._px(760)
        self.root.minsize(self._px(850), self._px(520))
        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r"\d+x\d+(?:[+-]\d+){2}", geometry):
            self.root.geometry(geometry)
        else:
            x = max(0, (self.root.winfo_screenwidth() - width) // 2)
            y = max(0, (self.root.winfo_screenheight() - height) // 2)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.configure(bg="#17191d")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#202329")
        style.configure("Panel.TFrame", background="#252a31")
        style.configure("TLabel", background="#252a31", foreground="#e5e7eb", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#252a31", foreground="#a7b0bd", font=("Segoe UI", 9))
        style.configure("Count.TLabel", background="#202329", foreground="#b9c2ce", font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground="#171b21", foreground="#f3f4f6", insertcolor="#ffffff",
                        bordercolor="#424a55", lightcolor="#424a55", darkcolor="#424a55", padding=6)
        style.map("TEntry", fieldbackground=[("disabled", "#252a31")], foreground=[("disabled", "#888f99")])
        style.configure("TCombobox", fieldbackground="#171b21", background="#343b45", foreground="#f3f4f6",
                        arrowcolor="#e5e7eb", bordercolor="#424a55", padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", "#171b21")], foreground=[("readonly", "#f3f4f6")],
                  selectbackground=[("readonly", "#2563eb")], selectforeground=[("readonly", "#ffffff")])
        style.configure("Treeview", background="#1b1f25", fieldbackground="#1b1f25", foreground="#e5e7eb",
                        rowheight=self._px(29), borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#303741", foreground="#f3f4f6",
                        relief="flat", font=("Segoe UI", 9, "bold"), padding=(8, 8))
        style.map("Treeview.Heading", background=[("active", "#3b4654")])
        style.map("Treeview", background=[("selected", "#244d78")], foreground=[("selected", "#ffffff")])
        style.configure("Vertical.TScrollbar", background="#343b45", troughcolor="#1b1f25",
                        bordercolor="#1b1f25", arrowcolor="#d1d5db")
        style.configure("Horizontal.TScrollbar", background="#343b45", troughcolor="#1b1f25",
                        bordercolor="#1b1f25", arrowcolor="#d1d5db")
        for name, color, active in (
            ("Accent", "#2563eb", "#1d4ed8"), ("Success", "#16834a", "#116b3b"),
            ("Info", "#087f8c", "#066874"), ("Neutral", "#3b424c", "#4b5563"),
        ):
            style.configure(f"{name}.TButton", background=color, foreground="#ffffff", borderwidth=0,
                            focusthickness=0, padding=(12, 7), font=("Segoe UI", 9, "bold"))
            style.map(f"{name}.TButton", background=[("disabled", "#41464e"), ("pressed", active), ("active", active)],
                      foreground=[("disabled", "#9299a3")])
        style.configure("TProgressbar", troughcolor="#171b21", background="#2c91e8",
                        bordercolor="#171b21", lightcolor="#2c91e8", darkcolor="#2c91e8")

    def _setup_ui(self) -> None:
        self.top_frame = ttk.Frame(self.root, style="Panel.TFrame", padding=(self._px(16), self._px(13)))
        self.top_frame.pack(fill=tk.X)

        path_row = ttk.Frame(self.top_frame, style="Panel.TFrame")
        path_row.pack(fill=tk.X, pady=(0, self._px(10)))
        self.lbl_target = ttk.Label(path_row, style="Muted.TLabel")
        self.lbl_target.pack(side=tk.LEFT, padx=(0, self._px(10)))
        self.path_var = tk.StringVar(value=self.target_directory)
        self.path_entry = ttk.Entry(path_row, textvariable=self.path_var, state="readonly")
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, self._px(10)))
        self.btn_browse = ttk.Button(path_row, style="Neutral.TButton", command=self._select_folder)
        self.btn_browse.pack(side=tk.RIGHT)

        controls = ttk.Frame(self.top_frame, style="Panel.TFrame")
        controls.pack(fill=tk.X)
        self.lbl_lang = ttk.Label(controls, style="Muted.TLabel")
        self.lbl_lang.pack(side=tk.LEFT, padx=(0, self._px(6)))
        self.lang_combo = ttk.Combobox(controls, state="readonly", width=10, values=["English", "Türkçe"])
        self.lang_combo.pack(side=tk.LEFT, padx=(0, self._px(18)))
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        self.lbl_separator = ttk.Label(controls, style="Muted.TLabel")
        self.lbl_separator.pack(side=tk.LEFT, padx=(0, self._px(6)))
        self.separator_combo = ttk.Combobox(controls, state="readonly", width=18)
        self.separator_combo.pack(side=tk.LEFT)
        self.separator_combo.bind("<<ComboboxSelected>>", self._on_separator_change)

        self.btn_export = ttk.Button(controls, style="Info.TButton", command=self._export_csv, state=tk.DISABLED)
        self.btn_export.pack(side=tk.RIGHT, padx=(self._px(7), 0))
        self.btn_scan = ttk.Button(controls, style="Success.TButton", command=self._start_scan)
        self.btn_scan.pack(side=tk.RIGHT, padx=(self._px(7), 0))

        search_row = ttk.Frame(self.root, style="TFrame", padding=(self._px(16), self._px(10)))
        search_row.pack(fill=tk.X)
        self.lbl_search = ttk.Label(search_row, style="Muted.TLabel")
        self.lbl_search.pack(side=tk.LEFT, padx=(0, self._px(8)))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var, width=36)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=False)
        self.search_var.trace_add("write", self._on_search_changed)
        self.btn_clear = ttk.Button(search_row, style="Neutral.TButton", command=self._clear_search)
        self.btn_clear.pack(side=tk.LEFT, padx=(self._px(6), 0))
        self.duplicates_only = ttk.Checkbutton(
            search_row, variable=self.duplicates_only_var, command=self._on_filter_changed,
        )
        self.duplicates_only.pack(side=tk.LEFT, padx=(self._px(12), 0))
        self.count_label = ttk.Label(search_row, style="Count.TLabel")
        self.count_label.pack(side=tk.RIGHT)

        table_frame = ttk.Frame(self.root, style="TFrame", padding=(self._px(16), 0, self._px(16), self._px(10)))
        table_frame.pack(fill=tk.BOTH, expand=True)
        self.columns = ("name", "folder", "size", "pages", "date", "duplicate", "path")
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings", selectmode="extended")
        widths = {"name": 235, "folder": 150, "size": 92, "pages": 76, "date": 142, "duplicate": 105, "path": 390}
        for column in self.columns:
            self.tree.column(column, width=self._px(widths[column]), minwidth=self._px(60),
                             anchor=tk.CENTER if column in {"size", "pages", "date", "duplicate"} else tk.W,
                             stretch=column in {"name", "path"})
            self.tree.heading(column, text="", command=lambda c=column: self._sort_by(c))
        self.tree.tag_configure("even", background="#1b1f25")
        self.tree.tag_configure("odd", background="#20252c")
        self.tree.tag_configure("corrupted", foreground="#ff7777")
        self.tree.tag_configure("encrypted", foreground="#f0be67")
        self.tree.tag_configure("unreadable", foreground="#ff9999")
        scrollbar_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", self._open_selected)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Button-2>", self._show_context_menu)

        bottom = ttk.Frame(self.root, style="Panel.TFrame", padding=(self._px(16), self._px(9)))
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_status = ttk.Label(bottom, style="Muted.TLabel", anchor=tk.W)
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress = ttk.Progressbar(bottom, orient=tk.HORIZONTAL, length=self._px(280), mode="determinate")
        self.progress.pack(side=tk.RIGHT, padx=(self._px(12), 0))
        # Packed only after a scan that skipped folders; see _finish_scan.
        self.btn_skipped = ttk.Button(bottom, style="Neutral.TButton", command=self._show_skipped_folders)

        self._bind_shortcuts()
        self._update_count_label()

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-f>", lambda _e: self._focus_search())
        self.root.bind_all("<Control-o>", lambda _e: self._select_folder())
        self.root.bind_all("<Control-r>", lambda _e: self._start_scan() if not self.is_scanning else self._cancel_scan())
        self.root.bind_all("<Control-e>", lambda _e: self._export_csv())
        self.root.bind_all("<Control-a>", self._select_all_visible)
        self.root.bind_all("<Escape>", lambda _e: self._clear_search())
        self.root.bind_all("<Control-Shift-c>", self._copy_selected_path)

    # ---------- Language, settings and status ----------
    def _update_language(self) -> None:
        self.root.title(self._t("title"))
        self.lbl_target.config(text=self._t("target_dir"))
        self.lbl_lang.config(text=self._t("language"))
        self.lbl_separator.config(text=self._t("csv_separator"))
        self.lbl_search.config(text=self._t("search"))
        self.btn_browse.config(text=self._t("browse"))
        self.btn_export.config(text=self._t("export"))
        self.btn_scan.config(text=self._t("cancel_scan" if self.is_scanning else "scan"))
        self.btn_clear.config(text=self._t("clear"))
        self.duplicates_only.config(text=self._t("duplicates_only"))
        self.btn_skipped.config(text=self._t("skipped_button", count=len(self._skipped_folders)))
        self.lang_combo.set("Türkçe" if self.current_lang == "tr" else "English")
        sep_keys = ("auto", "comma", "semicolon", "tab")
        self._separator_labels = {self._t("sep_" + key): key for key in sep_keys}
        self.separator_combo.configure(values=list(self._separator_labels.keys()))
        self.separator_combo.set(next(label for label, key in self._separator_labels.items() if key == self.csv_separator))
        heading_keys = {
            "name": "col_name", "folder": "col_folder", "size": "col_size", "pages": "col_pages",
            "date": "col_date", "duplicate": "col_duplicate", "path": "col_path",
        }
        for column, key in heading_keys.items():
            heading = self._t(key)
            if self._sort_column == column:
                heading += "  " + ("▼" if self._sort_reverse else "▲")
            self.tree.heading(column, text=heading)
        self._render_last_status()
        self._update_count_label()

    def _on_language_change(self, _event: Any = None) -> None:
        self.current_lang = "tr" if self.lang_combo.get() == "Türkçe" else "en"
        self._save_settings()
        self._update_language()
        self._queue_table_refresh(full=True)

    def _on_separator_change(self, _event: Any = None) -> None:
        self.csv_separator = self._separator_labels.get(self.separator_combo.get(), "auto")
        self._save_settings()

    def _set_status(self, key: str, **kwargs: Any) -> None:
        self._last_status = (key, kwargs)
        self._render_last_status()

    def _render_last_status(self) -> None:
        if not hasattr(self, "lbl_status"):
            return
        key, kwargs = self._last_status
        text = self._t(key, **kwargs)
        if not PYPDF_AVAILABLE and key in {"status_ready", "status_done", "status_cancelled", "status_no_pdf"}:
            text += self._t("status_missing_library")
        self.lbl_status.config(text=text)

    def _append_library_warning(self) -> None:
        # The warning is appended by _render_last_status so language switches remain in sync.
        self._render_last_status()

    # ---------- Folder and scan controls ----------
    def _select_folder(self) -> None:
        if self.is_scanning:
            return
        selected = filedialog.askdirectory(initialdir=self.target_directory, title=self._t("choose_folder"))
        if selected:
            self.target_directory = os.path.normpath(selected)
            self.path_var.set(self.target_directory)
            self._save_settings()
            self._set_status("status_ready")

    def _start_scan(self) -> None:
        if self.is_scanning:
            self._cancel_scan()
            return
        root_path = Path(self.target_directory).expanduser()
        if not root_path.exists() or not root_path.is_dir():
            messagebox.showerror(self._t("msg_error"), self._t("msg_invalid_folder"))
            return

        self.records.clear()
        self._insertion_order.clear()
        self._iid_by_path.clear()
        self._path_by_iid.clear()
        self._pending_render_paths.clear()
        self._pending_render_set.clear()
        self._visible_paths.clear()
        self.tree.delete(*self.tree.get_children())
        self.search_var.set("")
        self._table_mode = None
        self._sort_column = None
        self._sort_reverse = False
        self._update_language()
        self._cancel_event = threading.Event()
        self._scan_progress = 0
        self._scan_total = 0
        self._skipped_dirs = 0
        self._skipped_folders = []
        self.btn_skipped.pack_forget()
        self.progress.stop()
        self.progress.configure(mode="indeterminate", maximum=100)
        self.progress.start(12)
        self.is_scanning = True
        self.btn_scan.configure(text=self._t("cancel_scan"))
        self.btn_browse.configure(state=tk.DISABLED)
        self.lang_combo.configure(state="readonly")
        self.btn_export.configure(state=tk.DISABLED)
        self._set_status("status_discovering", files=0, folders=0)
        self._scan_thread = threading.Thread(target=self._scan_worker, args=(root_path,), daemon=True,
                                             name="PDFInventoryScanner")
        self._scan_thread.start()

    def _cancel_scan(self) -> None:
        if self.is_scanning:
            self._cancel_event.set()
            self.btn_scan.configure(state=tk.DISABLED)
            self._set_status("status_cancelling")

    @staticmethod
    def _discover_pdfs(root_path: Path, cancel_event: threading.Event,
                       emit_progress: Any) -> tuple[list[Path], list[tuple[str, str]]]:
        """Return discovered PDFs and (path, reason) pairs for skipped directories."""
        pdfs: list[Path] = []
        skipped: list[tuple[str, str]] = []
        visited_dirs = 0
        stack = [root_path]
        while stack and not cancel_event.is_set():
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if cancel_event.is_set():
                            break
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                directory = Path(entry.path)
                                reason = "link" if is_link_or_junction(entry) else skip_reason(directory)
                                if reason:
                                    skipped.append((entry.path, reason))
                                else:
                                    stack.append(directory)
                            elif entry.is_file(follow_symlinks=False):
                                if entry.name.startswith("._"):
                                    continue
                                if entry.name.casefold().endswith(".pdf"):
                                    pdfs.append(Path(entry.path))
                        except OSError:
                            # Individual entries can disappear or become inaccessible mid-scan.
                            continue
            except OSError:
                if current == root_path:
                    raise
                skipped.append((str(current), "access"))
            visited_dirs += 1
            if visited_dirs % 20 == 0:
                emit_progress(len(pdfs), visited_dirs, len(skipped))
        emit_progress(len(pdfs), visited_dirs, len(skipped))
        return pdfs, skipped

    def _scan_worker(self, root_path: Path) -> None:
        summary: dict[str, Any] = {"cancelled": False, "skipped_dirs": 0, "skipped_folders": []}
        try:
            pdf_paths, skipped_folders = self._discover_pdfs(
                root_path, self._cancel_event,
                lambda found, folders, skipped: self._queue.put(("discovering", (found, folders, skipped))),
            )
            summary["skipped_dirs"] = len(skipped_folders)
            summary["skipped_folders"] = skipped_folders
            if self._cancel_event.is_set():
                summary["cancelled"] = True
                self._queue.put(("done", summary))
                return

            total = len(pdf_paths)
            self._queue.put(("scan_total", total))
            if total == 0:
                self._queue.put(("done", summary))
                return

            max_workers = MAX_SCAN_WORKERS
            max_in_flight = max_workers * MAX_IN_FLIGHT_PER_WORKER
            inspected: dict[str, dict[str, Any]] = {}
            size_groups: dict[int, list[Path]] = defaultdict(list)
            completed = 0
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="PDFInspect") as executor:
                paths = iter(pdf_paths)
                pending: dict[Any, Path] = {}
                for _ in range(min(max_in_flight, total)):
                    path = next(paths)
                    pending[executor.submit(inspect_pdf, path)] = path
                while pending:
                    if self._cancel_event.is_set():
                        for future in pending:
                            future.cancel()
                        break
                    finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        path = pending.pop(future)
                        if self._cancel_event.is_set():
                            for queued in pending:
                                queued.cancel()
                            break
                        try:
                            record = future.result()
                        except Exception as exc:  # Defensive boundary for unexpected worker failures.
                            record = {
                                "path": str(path), "name": path.name, "folder": path.parent.name,
                                "size_bytes": None, "mtime": None, "mtime_ns": None, "pages": None,
                                "page_state": "unreadable", "duplicate": False, "quick_hash": None,
                                "error": str(exc), "file_id": None,
                            }
                        inspected[str(path)] = record
                        if record.get("size_bytes") is not None:
                            size_groups[record["size_bytes"]].append(path)
                        self._queue.put(("file", dict(record)))
                        completed += 1
                        self._queue.put(("inspect_progress", (completed, total)))
                    if self._cancel_event.is_set():
                        break
                    while len(pending) < max_in_flight:
                        try:
                            path = next(paths)
                        except StopIteration:
                            break
                        pending[executor.submit(inspect_pdf, path)] = path

            if self._cancel_event.is_set():
                summary["cancelled"] = True
                self._queue.put(("done", summary))
                return

            # Hard links share one file: hash only the first path and give the others its result.
            hard_link_of: dict[str, str] = {}
            candidates: list[dict[str, Any]] = []
            for group in size_groups.values():
                first_path_by_id: dict[Any, str] = {}
                distinct: list[dict[str, Any]] = []
                for path in group:
                    record = inspected.get(str(path))
                    if not record or record.get("size_bytes") is None:
                        continue
                    file_id = record.get("file_id")
                    if file_id is not None and file_id in first_path_by_id:
                        hard_link_of[record["path"]] = first_path_by_id[file_id]
                        continue
                    if file_id is not None:
                        first_path_by_id[file_id] = record["path"]
                    distinct.append(record)
                if len(distinct) > 1:
                    for record in distinct:
                        record["duplicate"] = None
                        candidates.append(record)
                        self._queue.put(("file_update", dict(record)))

            # Stage 1: a small partial hash narrows same-size files to likely matches.
            quick_results: dict[str, str | None] = {}
            if candidates:
                self._queue.put(("hash_stage", ("quick", len(candidates))))
                quick_done = 0
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="PDFQuickHash") as executor:
                    records = iter(candidates)
                    futures: dict[Any, dict[str, Any]] = {}
                    for _ in range(min(max_in_flight, len(candidates))):
                        rec = next(records)
                        futures[executor.submit(_quick_hash, Path(rec["path"]), rec["size_bytes"], rec["mtime_ns"])] = rec
                    while futures:
                        if self._cancel_event.is_set():
                            for pending in futures:
                                pending.cancel()
                            break
                        finished, _ = wait(futures, return_when=FIRST_COMPLETED)
                        for future in finished:
                            rec = futures.pop(future)
                            if self._cancel_event.is_set():
                                for pending in futures:
                                    pending.cancel()
                                break
                            try:
                                value = future.result()
                            except OSError:
                                value = None
                            quick_results[rec["path"]] = value
                            quick_done += 1
                            self._queue.put(("hash_progress", ("quick", quick_done, len(candidates))))
                        while not self._cancel_event.is_set() and len(futures) < max_in_flight:
                            try:
                                rec = next(records)
                            except StopIteration:
                                break
                            futures[executor.submit(_quick_hash, Path(rec["path"]), rec["size_bytes"], rec["mtime_ns"])] = rec
                if self._cancel_event.is_set():
                    summary["cancelled"] = True
                    self._queue.put(("done", summary))
                    return

            likely_groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
            for rec in candidates:
                quick = quick_results.get(rec["path"])
                if quick:
                    likely_groups[(rec["size_bytes"], quick)].append(rec)
            full_candidates = [rec for group in likely_groups.values() if len(group) > 1 for rec in group]

            # Same-size files with different partial hashes are definitely not duplicates.
            duplicate_states: dict[str, bool | None] = {rec["path"]: False for rec in candidates}
            for rec in candidates:
                if quick_results.get(rec["path"]) is None:
                    duplicate_states[rec["path"]] = None

            if full_candidates:
                self._queue.put(("hash_stage", ("full", len(full_candidates))))
                full_results: dict[str, str | None] = {}
                full_done = 0
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="PDFFullHash") as executor:
                    records = iter(full_candidates)
                    futures: dict[Any, dict[str, Any]] = {}
                    for _ in range(min(max_in_flight, len(full_candidates))):
                        rec = next(records)
                        futures[executor.submit(_full_hash, Path(rec["path"]), rec["size_bytes"], rec["mtime_ns"], self._cancel_event)] = rec
                    while futures:
                        if self._cancel_event.is_set():
                            for pending in futures:
                                pending.cancel()
                            break
                        finished, _ = wait(futures, return_when=FIRST_COMPLETED)
                        for future in finished:
                            rec = futures.pop(future)
                            if self._cancel_event.is_set():
                                for pending in futures:
                                    pending.cancel()
                                break
                            try:
                                value = future.result()
                            except OSError:
                                value = None
                            full_results[rec["path"]] = value
                            full_done += 1
                            self._queue.put(("hash_progress", ("full", full_done, len(full_candidates))))
                        while not self._cancel_event.is_set() and len(futures) < max_in_flight:
                            try:
                                rec = next(records)
                            except StopIteration:
                                break
                            futures[executor.submit(_full_hash, Path(rec["path"]), rec["size_bytes"], rec["mtime_ns"], self._cancel_event)] = rec
                if self._cancel_event.is_set():
                    summary["cancelled"] = True
                    self._queue.put(("done", summary))
                    return

                digest_groups: dict[str, list[str]] = defaultdict(list)
                for path, digest in full_results.items():
                    if digest:
                        digest_groups[digest].append(path)
                    else:
                        duplicate_states[path] = None
                for same_content_paths in digest_groups.values():
                    if len(same_content_paths) > 1:
                        for path in same_content_paths:
                            duplicate_states[path] = True

            for path, first_path in hard_link_of.items():
                duplicate_states[path] = duplicate_states.get(first_path, False)
            for path, state in duplicate_states.items():
                record = inspected.get(path)
                if record:
                    record["duplicate"] = state
            self._queue.put(("duplicates", duplicate_states))
            summary["cancelled"] = self._cancel_event.is_set()
            self._queue.put(("done", summary))
        except Exception as exc:
            logging.exception("Unexpected scanner failure")
            summary["error"] = str(exc)
            summary["cancelled"] = self._cancel_event.is_set()
            self._queue.put(("done", summary))

    def _poll_worker_queue(self) -> None:
        if self._closing:
            return
        changed = False
        processed = 0
        while processed < 1200:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            processed += 1
            if kind == "discovering":
                found, folders, skipped = payload
                self._skipped_dirs = skipped
                self._set_status("status_discovering", files=found, folders=folders)
            elif kind == "scan_total":
                self.progress.stop()
                self.progress.configure(mode="determinate", maximum=max(1, payload), value=0)
                self._scan_total = payload
                self._set_status("status_scanning", current=0, total=payload)
            elif kind in {"file", "file_update"}:
                record = payload
                path = record["path"]
                if path not in self.records:
                    self._insertion_order.append(path)
                self.records[path] = record
                self._mark_path_dirty(path)
                changed = True
                if len(self.records) > 0:
                    self.btn_export.configure(state=tk.NORMAL)
            elif kind == "inspect_progress":
                current, total = payload
                self.progress.configure(value=current, maximum=max(1, total))
                self._scan_progress = current
                self._set_status("status_scanning", current=current, total=total)
            elif kind == "hash_stage":
                stage, total = payload
                self.progress.configure(value=0, maximum=max(1, total))
                self._set_status("status_hashing_quick" if stage == "quick" else "status_hashing_full",
                                 current=0, total=total)
            elif kind == "hash_progress":
                stage, current, total = payload
                self.progress.configure(value=current, maximum=max(1, total))
                self._set_status("status_hashing_quick" if stage == "quick" else "status_hashing_full",
                                 current=current, total=total)
            elif kind == "duplicates":
                for path, state in payload.items():
                    if path in self.records:
                        self.records[path]["duplicate"] = state
                        self._mark_path_dirty(path)
                changed = True
            elif kind == "worker_error":
                self._set_status("status_scan_error", error=payload)
            elif kind == "done":
                self._finish_scan(payload)
                changed = True
        if changed:
            self._refresh_table()
        self._update_count_label()
        self.root.after(100, self._poll_worker_queue)

    def _finish_scan(self, summary: dict[str, Any]) -> None:
        self.is_scanning = False
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100)
        self.progress.configure(value=100 if self.records else 0)
        self.btn_scan.configure(state=tk.NORMAL, text=self._t("scan"))
        self.btn_browse.configure(state=tk.NORMAL)
        self.lang_combo.configure(state="readonly")
        self.btn_export.configure(state=tk.NORMAL if self.records else tk.DISABLED)
        self._skipped_dirs = int(summary.get("skipped_dirs", self._skipped_dirs))
        self._skipped_folders = list(summary.get("skipped_folders", []))
        if self._skipped_folders:
            self.btn_skipped.config(text=self._t("skipped_button", count=len(self._skipped_folders)))
            # Packed before the status label so a long status message cannot squeeze it out.
            self.btn_skipped.pack(side=tk.RIGHT, padx=(self._px(12), 0), before=self.lbl_status)
        count = len(self.records)
        duplicates = sum(1 for rec in self.records.values() if rec.get("duplicate") is True)
        corrupt = sum(1 for rec in self.records.values() if rec.get("page_state") == "corrupt")
        errors = sum(1 for rec in self.records.values() if rec.get("page_state") == "unreadable")
        if summary.get("error"):
            self._set_status("status_scan_error", error=summary["error"])
        elif summary.get("cancelled"):
            self._set_status("status_cancelled", count=count, duplicates=duplicates)
        elif count == 0:
            self._set_status("status_no_pdf")
        else:
            self._set_status("status_done", count=count, duplicates=duplicates, corrupt=corrupt,
                             errors=errors, skipped=self._skipped_dirs)
        self._save_settings()

    def _show_skipped_folders(self) -> None:
        limit = 40
        lines = [self._t("skipped_intro"), ""]
        lines += [f"{self._t('skip_reason_' + reason)}: {path}" for path, reason in self._skipped_folders[:limit]]
        if len(self._skipped_folders) > limit:
            lines += ["", self._t("skipped_more", count=len(self._skipped_folders) - limit)]
        messagebox.showinfo(self._t("skipped_title"), "\n".join(lines))

    # ---------- Table, filtering and sorting ----------
    def _mark_path_dirty(self, path: str) -> None:
        if path not in self._pending_render_set:
            self._pending_render_paths.append(path)
            self._pending_render_set.add(path)

    def _queue_table_refresh(self, full: bool = False) -> None:
        if full:
            self._table_mode = None
        self._refresh_table()

    def _on_search_changed(self, *_args: Any) -> None:
        if self._search_after_id:
            try:
                self.root.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
        self._search_after_id = self.root.after(160, self._apply_search)

    def _apply_search(self) -> None:
        self._search_after_id = None
        self._queue_table_refresh(full=True)
        self._update_count_label()

    def _clear_search(self) -> None:
        if self.search_var.get():
            self.search_var.set("")
            self.search_entry.focus_set()

    def _focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)

    def _sort_by(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self._queue_table_refresh(full=True)
        self._update_language()

    def _sort_value(self, record: dict[str, Any], column: str) -> Any:
        if column == "size":
            return record.get("size_bytes") if record.get("size_bytes") is not None else -1
        if column == "pages":
            return record.get("pages") if record.get("pages") is not None else -1
        if column == "date":
            return record.get("mtime") if record.get("mtime") is not None else -1
        if column == "duplicate":
            state = record.get("duplicate")
            return -1 if state is None else int(bool(state))
        if column == "folder":
            return normalize_search(record.get("folder", ""))
        if column == "path":
            return normalize_search(record.get("path", ""))
        return normalize_search(record.get("name", ""))

    def _filtered_records(self) -> list[dict[str, Any]]:
        query = normalize_search(self.search_var.get().strip())
        records = list(self.records.values())
        if self.duplicates_only_var.get():
            records = [rec for rec in records if rec.get("duplicate") is True]
        if query:
            records = [rec for rec in records if query in normalize_search(
                " ".join((rec.get("name", ""), rec.get("folder", ""), rec.get("path", ""),
                          self._page_display(rec), self._duplicate_display(rec)))
            )]
        if self._sort_column:
            records.sort(key=lambda rec: (self._sort_value(rec, self._sort_column), normalize_search(rec.get("path", ""))),
                         reverse=self._sort_reverse)
        else:
            order = {path: index for index, path in enumerate(self._insertion_order)}
            records.sort(key=lambda rec: order.get(rec["path"], 0))
        return records

    def _on_filter_changed(self) -> None:
        self._queue_table_refresh(full=True)
        self._update_count_label()

    def _refresh_table(self) -> None:
        query = normalize_search(self.search_var.get().strip())
        mode = (query, self._sort_column, self._sort_reverse, self.duplicates_only_var.get())
        selected_paths = {self._path_by_iid[iid] for iid in self.tree.selection() if iid in self._path_by_iid}
        incremental = not query and self._sort_column is None and self._table_mode == mode
        if incremental:
            pending = self._pending_render_paths
            self._pending_render_paths = []
            self._pending_render_set.clear()
            for path in pending:
                record = self.records.get(path)
                if not record:
                    continue
                iid = self._iid_for_path(path)
                already_visible = self.tree.exists(iid)
                if mode[3] and record.get("duplicate") is not True:
                    if already_visible:
                        self.tree.delete(iid)
                        self._path_by_iid.pop(iid, None)
                        self._visible_paths.remove(path)
                    continue
                values = self._row_values(record)
                tags = self._row_tags(record, len(self._iid_by_path))
                if already_visible:
                    self.tree.item(iid, values=values, tags=tags)
                else:
                    self.tree.insert("", tk.END, iid=iid, values=values, tags=tags)
                    self._visible_paths.append(path)
        else:
            visible = self._filtered_records()
            self.tree.delete(*self.tree.get_children())
            self._iid_by_path.clear()
            self._path_by_iid.clear()
            self._visible_paths = []
            for index, record in enumerate(visible):
                path = record["path"]
                iid = self._iid_for_path(path)
                self.tree.insert("", tk.END, iid=iid, values=self._row_values(record), tags=self._row_tags(record, index))
                self._iid_by_path[path] = iid
                self._path_by_iid[iid] = path
                self._visible_paths.append(path)
                if path in selected_paths:
                    self.tree.selection_add(iid)
            self._pending_render_paths.clear()
            self._pending_render_set.clear()
        self._table_mode = mode
        self._update_count_label()

    def _iid_for_path(self, path: str) -> str:
        iid = self._iid_by_path.get(path)
        if iid:
            return iid
        iid = "pdf_" + hashlib.sha256(path.encode("utf-8", errors="surrogatepass")).hexdigest()
        self._iid_by_path[path] = iid
        self._path_by_iid[iid] = path
        return iid

    def _row_tags(self, record: dict[str, Any], index: int) -> tuple[str, ...]:
        tags = ["even" if index % 2 == 0 else "odd"]
        state = record.get("page_state")
        if state == "corrupt":
            tags.append("corrupted")
        elif state == "encrypted":
            tags.append("encrypted")
        elif state == "unreadable":
            tags.append("unreadable")
        return tuple(tags)

    def _format_size(self, size: int | None) -> str:
        if size is None:
            return "—"
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{value:.1f} PB"

    def _page_display(self, record: dict[str, Any]) -> str:
        state = record.get("page_state")
        if state == "ok":
            return str(record.get("pages", 0))
        keys = {
            "corrupt": "page_corrupt", "encrypted": "page_encrypted",
            "unavailable": "page_unavailable", "unreadable": "page_unreadable",
            "pending": "pending",
        }
        return self._t(keys.get(state, "page_unavailable"))

    def _duplicate_display(self, record: dict[str, Any]) -> str:
        state = record.get("duplicate")
        if state is True:
            return self._t("yes")
        if state is False:
            return self._t("no")
        return self._t("pending") if self.is_scanning else self._t("unknown")

    def _row_values(self, record: dict[str, Any]) -> tuple[str, ...]:
        mtime = record.get("mtime")
        try:
            date_text = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime is not None else "—"
        except (OSError, OverflowError, ValueError):
            date_text = "—"
        return (
            str(record.get("name", "")), str(record.get("folder", "")),
            self._format_size(record.get("size_bytes")), self._page_display(record), date_text,
            self._duplicate_display(record), str(record.get("path", "")),
        )

    def _update_count_label(self) -> None:
        if not hasattr(self, "count_label"):
            return
        visible = len(self._filtered_records()) if self._table_mode != (
            "", None, False, self.duplicates_only_var.get()
        ) else len(self._visible_paths)
        self.count_label.config(text=self._t("count_label", visible=visible, total=len(self.records)))

    # ---------- Context actions and keyboard shortcuts ----------
    def _show_context_menu(self, event: Any) -> str:
        row = self.tree.identify_row(event.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            menu = tk.Menu(self.root, tearoff=False, bg="#252a31", fg="#f3f4f6",
                           activebackground="#2563eb", activeforeground="#ffffff")
            menu.add_command(label=self._t("open_file"), command=self._open_selected)
            menu.add_command(label=self._t("open_folder"), command=self._open_selected_folder)
            menu.add_separator()
            menu.add_command(label=self._t("copy_path"), command=self._copy_selected_path)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        return "break"

    def _selected_paths(self) -> list[str]:
        return [self._path_by_iid[iid] for iid in self.tree.selection() if iid in self._path_by_iid]

    def _on_double_click(self, event: Any) -> None:
        if self.tree.identify_region(event.x, event.y) == "cell":
            self._open_selected()

    def _open_selected(self, _event: Any = None) -> str:
        paths = self._selected_paths()
        if paths:
            self._open_path(paths[0])
        return "break"

    def _open_selected_folder(self) -> None:
        paths = self._selected_paths()
        if paths:
            self._open_path(str(Path(paths[0]).parent))

    def _open_path(self, path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror(self._t("msg_error"), self._t("msg_file_error", error=exc))

    def _copy_selected_path(self, _event: Any = None) -> str:
        paths = self._selected_paths()
        if paths:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(paths[0])
                self._set_status("copied")
            except tk.TclError as exc:
                messagebox.showerror(self._t("msg_error"), self._t("msg_copy_error", error=exc))
        return "break"

    def _select_all_visible(self, _event: Any = None) -> str | None:
        # Preserve the normal Ctrl+A text-selection behavior inside the search box.
        if self.root.focus_get() == self.search_entry:
            return None
        children = self.tree.get_children("")
        if children:
            self.tree.selection_set(children)
        return "break"

    # ---------- CSV export ----------
    def _export_csv(self) -> None:
        visible_records = self._filtered_records()
        if not visible_records:
            messagebox.showwarning(self._t("msg_warning"), self._t("msg_no_data"))
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{self._t('filename_prefix')}_{timestamp}.csv"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=self.last_export_dir, initialfile=default_name, title=self._t("choose_export"),
        )
        if not save_path:
            return

        headers = [self._t("col_" + key) for key in self.columns]
        delimiter = resolve_csv_delimiter(self.csv_separator, self.current_lang)
        destination = Path(save_path)
        try:
            write_csv_export(destination, headers, (self._row_values(record) for record in visible_records), delimiter)
            self.last_export_dir = str(destination.parent)
            self._save_settings()
            self._set_status("status_exported", count=len(visible_records), path=str(destination))
        except (OSError, csv.Error, UnicodeError) as exc:
            messagebox.showerror(self._t("msg_error"), self._t("msg_export_error", error=exc))

    # ---------- Lifecycle ----------
    def _on_close(self) -> None:
        self._closing = True
        if self.is_scanning:
            self._cancel_event.set()
        self._save_settings()
        self.root.destroy()


def ctypes_lang_id() -> int:
    """Read the Windows UI language without making ctypes a hard dependency."""
    try:
        import ctypes
        return int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
    except Exception:
        return 0


def enable_windows_dpi_awareness() -> None:
    """Ask Windows for per-monitor DPI awareness before constructing Tk."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main() -> None:
    enable_windows_dpi_awareness()
    root = tk.Tk()
    PDFInventoryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
