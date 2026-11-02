#!/usr/bin/env python3
"""PDF Master Suite - responsive PDF inventory for Windows, macOS and Linux.

Open-source project by Kerem Aydın (https://keremaydin.net).
"""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import locale
import logging
import math
from logging.handlers import RotatingFileHandler
import os
import queue
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import webbrowser
import zlib
from collections import defaultdict
from dataclasses import dataclass, replace
from functools import lru_cache
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
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
        "search_hint": "Search name, folder or path…",
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
        "status_done": "Done: {count} PDFs · {duplicates} duplicate files in {groups} groups ({reclaimable} reclaimable) · {corrupt} corrupted · {errors} unreadable · {skipped} folders skipped.",
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
        "col_problem": "Problem",
        "col_size_bytes": "Size (bytes)",
        "dup_group": "Yes · group {group}",
        "csv_files": "CSV files",
        "all_files": "All files",
        "menu_file": "File",
        "menu_tools": "Tools",
        "menu_select_folder": "Select folder…",
        "menu_exit": "Exit",
        "menu_resources": "Resource usage",
        "resources_detected": "This PC: {cpus} logical processors",
        "resource_low": "Low — {workers} thread(s), background priority",
        "resource_medium": "Medium — {workers} threads (default)",
        "resource_high": "High — {workers} threads, fastest",
        "status_resources": "Resource usage set to {level}: {workers} scan threads. You can also change it during a scan.",
        "resource_notice_up": "Speed increased to {level} ({workers} threads), applied to the remaining files",
        "resource_notice_down": "Speed lowered to {level} ({workers} threads), applied to the remaining files",
        "level_low": "Low",
        "level_medium": "Medium",
        "level_high": "High",
        "tool_clean": "Clean PDF filenames…",
        "tool_undo": "Undo a filename cleanup…",
        "btn_clean": "Clean names…",
        "btn_export": "Export CSV",
        "settings_hint": "Settings: language and CSV separator",
        "empty_hint": "Choose a folder, then press Start scan (Ctrl+R).",
        "resource_choice": "{level} · {workers} thread(s)",
        "menu_help": "Help",
        "menu_about": "About…",
        "about_title": "About PDF Master Suite",
        "about_text": "PDF Master Suite — Inventory\n\nAn open-source project coded by Kerem Aydın.\nhttps://keremaydin.net",
        "credit": "Open-source project by Kerem Aydın · keremaydin.net",
        "clean_title": "Clean PDF filenames",
        "clean_intro": "Removes the “(Z-Library)” and “(z-library.sk, 1lib.sk, z-lib.sk)” tags from the end of PDF names among the {total} visible rows. Only names change; file contents are never modified. A report is saved so you can undo the renames with Tools → Undo a filename cleanup.",
        "clean_none": "None of the {total} visible PDF names ends with a supported Z-Library tag.",
        "clean_apply": "Rename {count} files",
        "clean_done": "Renamed {renamed} of {total} files.\n\nUndo report:\n{report}",
        "undo_title": "Undo a filename cleanup",
        "undo_intro": "Restores the original names recorded in {report}.",
        "undo_ignored": "{count} report rows were ignored because they do not match a cleanup rename.",
        "undo_nothing": "This report has no completed renames to restore.",
        "undo_invalid": "This file cannot be used to undo a cleanup:\n{details}",
        "undo_apply": "Restore {count} names",
        "undo_done": "Restored {renamed} of {total} names.\n\nReport:\n{report}",
        "choose_report": "Select a cleanup report",
        "col_status": "Status",
        "col_current": "Current name",
        "col_new": "New name",
        "rename_status_ready": "Ready",
        "rename_status_collision": "Name taken",
        "rename_status_skipped": "File missing",
        "rename_status_error": "Error",
        "rename_status_renamed": "Renamed",
        "rename_counts": "{ready} ready · {blocked} cannot be renamed",
        "rename_problems": "{count} could not be renamed; the report lists why.",
        "cancel": "Cancel",
        "msg_report_error": "The rename report could not be created, so no files were renamed:\n{error}",
        "msg_report_final_error": "Files were renamed, but the report could not be saved:\n{error}\n\nThe renamed files are listed in the log file:\n{log}",
        "status_renamed": "Renamed {count} PDF filenames. Undo report saved.",
        "status_restored": "Restored {count} PDF filenames.",
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
        "search_hint": "Ad, klasör veya yolda ara…",
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
        "status_done": "Tamamlandı: {count} PDF · {groups} grupta {duplicates} yinelenen dosya ({reclaimable} kazanılabilir) · {corrupt} bozuk · {errors} okunamadı · {skipped} klasör atlandı.",
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
        "col_problem": "Sorun",
        "col_size_bytes": "Boyut (bayt)",
        "dup_group": "Evet · grup {group}",
        "csv_files": "CSV dosyaları",
        "all_files": "Tüm dosyalar",
        "menu_file": "Dosya",
        "menu_tools": "Araçlar",
        "menu_select_folder": "Klasör seç…",
        "menu_exit": "Çıkış",
        "menu_resources": "Kaynak kullanımı",
        "resources_detected": "Bu bilgisayar: {cpus} mantıksal işlemci",
        "resource_low": "Düşük — {workers} iş parçacığı, arka plan önceliği",
        "resource_medium": "Orta — {workers} iş parçacığı (varsayılan)",
        "resource_high": "Yüksek — {workers} iş parçacığı, en hızlı",
        "status_resources": "Kaynak kullanımı: {level}, {workers} tarama iş parçacığı. Tarama sırasında da değiştirilebilir.",
        "resource_notice_up": "Hız {level} seviyesine yükseltildi ({workers} iş parçacığı), kalan dosyalara uygulanıyor",
        "resource_notice_down": "Hız {level} seviyesine düşürüldü ({workers} iş parçacığı), kalan dosyalara uygulanıyor",
        "level_low": "Düşük",
        "level_medium": "Orta",
        "level_high": "Yüksek",
        "tool_clean": "PDF dosya adlarını temizle…",
        "tool_undo": "Dosya adı temizliğini geri al…",
        "btn_clean": "Adları temizle…",
        "btn_export": "CSV olarak aktar",
        "settings_hint": "Ayarlar: dil ve CSV ayırıcı",
        "empty_hint": "Bir klasör seçin, ardından Taramayı başlat'a basın (Ctrl+R).",
        "resource_choice": "{level} · {workers} iş parçacığı",
        "menu_help": "Yardım",
        "menu_about": "Hakkında…",
        "about_title": "PDF Master Suite hakkında",
        "about_text": "PDF Master Suite — Envanter\n\nKerem Aydın tarafından kodlanmış açık kaynaklı bir projedir.\nhttps://keremaydin.net",
        "credit": "Kerem Aydın tarafından geliştirilen açık kaynaklı proje · keremaydin.net",
        "clean_title": "PDF dosya adlarını temizle",
        "clean_intro": "Görünen {total} satırdaki PDF adlarının sonundaki “(Z-Library)” ve “(z-library.sk, 1lib.sk, z-lib.sk)” etiketlerini kaldırır. Yalnızca adlar değişir; dosya içerikleri asla değiştirilmez. Yeniden adlandırmaları Araçlar → Dosya adı temizliğini geri al ile geri alabilmeniz için bir rapor kaydedilir.",
        "clean_none": "Görünen {total} PDF adından hiçbiri desteklenen bir Z-Library etiketiyle bitmiyor.",
        "clean_apply": "{count} dosyayı yeniden adlandır",
        "clean_done": "{total} dosyadan {renamed} tanesi yeniden adlandırıldı.\n\nGeri alma raporu:\n{report}",
        "undo_title": "Dosya adı temizliğini geri al",
        "undo_intro": "{report} raporunda kayıtlı özgün adları geri yükler.",
        "undo_ignored": "Bir temizlik yeniden adlandırmasıyla eşleşmeyen {count} rapor satırı yok sayıldı.",
        "undo_nothing": "Bu raporda geri yüklenecek tamamlanmış yeniden adlandırma yok.",
        "undo_invalid": "Bu dosya bir temizliği geri almak için kullanılamaz:\n{details}",
        "undo_apply": "{count} adı geri yükle",
        "undo_done": "{total} addan {renamed} tanesi geri yüklendi.\n\nRapor:\n{report}",
        "choose_report": "Bir temizlik raporu seçin",
        "col_status": "Durum",
        "col_current": "Şimdiki ad",
        "col_new": "Yeni ad",
        "rename_status_ready": "Hazır",
        "rename_status_collision": "Ad kullanımda",
        "rename_status_skipped": "Dosya bulunamadı",
        "rename_status_error": "Hata",
        "rename_status_renamed": "Yeniden adlandırıldı",
        "rename_counts": "{ready} hazır · {blocked} yeniden adlandırılamaz",
        "rename_problems": "{count} dosya yeniden adlandırılamadı; nedenleri raporda.",
        "cancel": "İptal",
        "msg_report_error": "Yeniden adlandırma raporu oluşturulamadığı için hiçbir dosya yeniden adlandırılmadı:\n{error}",
        "msg_report_final_error": "Dosyalar yeniden adlandırıldı ancak rapor kaydedilemedi:\n{error}\n\nYeniden adlandırılan dosyalar günlük dosyasında listelenir:\n{log}",
        "status_renamed": "{count} PDF dosya adı değiştirildi. Geri alma raporu kaydedildi.",
        "status_restored": "{count} PDF dosya adı geri yüklendi.",
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
# Each worker may have one more task queued so it never waits for the scanner to hand out work.
MAX_IN_FLIGHT_PER_WORKER = 2
# Resource usage levels, from lightest to heaviest. Every launch starts at the default.
RESOURCE_LEVELS = ("low", "medium", "high")
DEFAULT_RESOURCE_LEVEL = "medium"
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
NORMAL_PRIORITY_CLASS = 0x20
# Backpressure prevents a fast scanner from retaining an unbounded number of
# pending UI updates while the main thread renders a large result set.
MAX_UI_QUEUE_EVENTS = 512
# A PDF parse that runs longer than this is reported as unreadable instead of stalling the scan.
INSPECT_TIMEOUT_SECONDS = 120
# Sorted or filtered tables rebuild at most this often while a scan streams in new rows.
SCAN_TABLE_REFRESH_SECONDS = 1.0
# How long a mid-scan resource level change stays visible next to the progress text.
RESOURCE_NOTICE_SECONDS = 8.0
LANGUAGE_NAMES = {"en": "English", "tr": "Türkçe"}
CSV_SEPARATORS = ("auto", "comma", "semicolon", "tab")


@dataclass(frozen=True)
class ResourceProfile:
    level: str
    workers: int
    hash_chunk: int
    background_priority: bool


def available_cpus() -> int:
    """Logical processors this process may use (respects CPU affinity on Python 3.13+)."""
    counter = getattr(os, "process_cpu_count", None) or os.cpu_count
    return max(1, counter() or 1)


def resource_profile(level: str, cpus: int | None = None) -> ResourceProfile:
    """Size scan concurrency and read buffers for a level on a machine with cpus processors."""
    cpus = cpus or available_cpus()
    if level == "low":
        # One or two threads with small reads and below-normal priority keep the PC responsive.
        return ResourceProfile("low", max(1, min(cpus // 4, 2)), 256 * 1024, True)
    if level == "high":
        # PDF reads also wait on disk or network, so a few extra threads still help on small CPUs.
        return ResourceProfile("high", max(4, min(cpus, 16)), 4 * 1024 * 1024, False)
    return ResourceProfile("medium", max(2, min(cpus // 2, 6)), FULL_HASH_CHUNK, False)


def apply_process_priority(background: bool) -> None:
    """Lower or restore this process's CPU priority. Windows only; elsewhere it is left alone,
    because an unprivileged process cannot raise its priority again after lowering it."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        # A private handle with declared types: the default int return truncates 64-bit handles.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        priority = BELOW_NORMAL_PRIORITY_CLASS if background else NORMAL_PRIORITY_CLASS
        if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), priority):
            logging.warning("Could not change process priority (error %s)", ctypes.get_last_error())  # type: ignore[attr-defined]
    except Exception:
        logging.exception("Could not change process priority")


class ResourceGovernor:
    """The active resource level. The scanner reads it while it runs, so a change applies mid-scan."""

    def __init__(self, level: str = DEFAULT_RESOURCE_LEVEL, cpus: int | None = None):
        self.cpus = cpus or available_cpus()
        self.profile = resource_profile(level if level in RESOURCE_LEVELS else DEFAULT_RESOURCE_LEVEL, self.cpus)

    @property
    def level(self) -> str:
        return self.profile.level

    def set_level(self, level: str) -> None:
        if level not in RESOURCE_LEVELS:
            raise ValueError(f"Unknown resource level: {level}")
        previous, self.profile = self.profile, resource_profile(level, self.cpus)
        if previous.background_priority != self.profile.background_priority:
            apply_process_priority(self.profile.background_priority)


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
               cancel_event: threading.Event | None = None, chunk_size: int = FULL_HASH_CHUNK) -> str | None:
    """Compute SHA-256 in bounded chunks and reject files changed mid-scan."""
    if cancel_event is not None and cancel_event.is_set():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                return None
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    after = path.stat()
    if after.st_size != expected_size:
        return None
    if expected_mtime_ns is not None and after.st_mtime_ns != expected_mtime_ns:
        return None
    return digest.hexdigest()


def _base_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path), "name": path.name, "folder": path.parent.name,
        "size_bytes": None, "mtime": None, "mtime_ns": None, "pages": None,
        "page_state": "unavailable" if not PYPDF_AVAILABLE else "pending",
        "duplicate": False, "duplicate_group": None, "error": None, "file_id": None,
    }


def _apply_stat(record: dict[str, Any], stat: os.stat_result) -> None:
    record.update(size_bytes=stat.st_size, mtime=stat.st_mtime, mtime_ns=stat.st_mtime_ns,
                  file_id=(stat.st_dev, stat.st_ino) if stat.st_ino else None)


def failed_record(path: Path, error: str) -> dict[str, Any]:
    """Build an unreadable record, keeping size and identity when the file can still be stat'ed."""
    record = _base_record(path)
    record.update(page_state="unreadable", error=error)
    try:
        _apply_stat(record, path.stat())
    except OSError:
        pass
    return record


def inspect_pdf(path: Path) -> dict[str, Any]:
    """Inspect one PDF without touching Tk; safe to call from a worker thread."""
    record = _base_record(path)
    try:
        _apply_stat(record, path.stat())
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
        record.update(page_state="corrupt", error=str(exc) or type(exc).__name__)
    return record


def discover_pdfs(root_path: Path, cancel_event: threading.Event,
                  emit_progress: Callable[[int, int, int], None]) -> tuple[list[Path], list[tuple[str, str]]]:
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


def bounded_map(fn: Callable[[Any], Any], items: Iterable[Any], cancel_event: threading.Event,
                on_result: Callable[[Any, Any, BaseException | None], None], *,
                timeout: float | None = None, name: str = "PDFWorker",
                governor: ResourceGovernor | None = None) -> bool:
    """Run fn over items on the governor's worker threads, keeping at most
    MAX_IN_FLIGHT_PER_WORKER tasks per worker submitted.

    on_result(item, result, error) runs on the calling thread. A task that runs longer than
    timeout seconds is reported with a TimeoutError and abandoned: its thread finishes in the
    background while queued work moves to a fresh pool. When the governor's worker count changes,
    queued work also moves to a fresh pool of the new size; running tasks finish where they are
    and still count toward the limit. Returns False when cancelled; cancelling does not wait for
    running tasks.
    """
    governor = governor or ResourceGovernor()
    source = iter(items)
    workers = governor.profile.workers
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
    pending: dict[Future[Any], tuple[Any, list[float | None]]] = {}

    def submit(item: Any) -> None:
        started: list[float | None] = [None]

        def run() -> Any:
            started[0] = time.monotonic()
            return fn(item)

        pending[executor.submit(run)] = (item, started)

    def restart_pool() -> None:
        nonlocal executor, workers
        requeue = [pending.pop(future)[0] for future in list(pending) if future.cancel()]
        executor.shutdown(wait=False)
        workers = governor.profile.workers
        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        for item in requeue:
            submit(item)

    def fill() -> None:
        if governor.profile.workers != workers:
            restart_pool()
        while len(pending) < workers * MAX_IN_FLIGHT_PER_WORKER and not cancel_event.is_set():
            try:
                item = next(source)
            except StopIteration:
                return
            submit(item)

    try:
        fill()
        while pending:
            if cancel_event.is_set():
                return False
            finished, _ = wait(pending, timeout=0.5 if timeout is not None else None,
                               return_when=FIRST_COMPLETED)
            for future in finished:
                item, _started = pending.pop(future)
                try:
                    result, error = future.result(), None
                except Exception as exc:  # Reported to the caller, which decides how to record it.
                    result, error = None, exc
                on_result(item, result, error)
            if timeout is not None:
                now = time.monotonic()
                stuck = [future for future, (_item, started) in pending.items()
                         if started[0] is not None and now - started[0] > timeout and not future.done()]
                if stuck:
                    for future in stuck:
                        item, _started = pending.pop(future)
                        on_result(item, None, TimeoutError(f"Timed out after {timeout:g} s"))
                    restart_pool()
            fill()
        return not cancel_event.is_set()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def scan_folder(root_path: Path, cancel_event: threading.Event, emit: Callable[[str, Any], None],
                governor: ResourceGovernor | None = None) -> None:
    """Discover, inspect and compare the PDFs below root_path, reporting through emit(kind, payload).

    Runs on a worker thread and never touches Tk. The last event is always ("done", summary).
    governor sets the thread count and read size, and may change while the scan runs.
    """
    governor = governor or ResourceGovernor()
    summary: dict[str, Any] = {"cancelled": False, "skipped_dirs": 0, "skipped_folders": []}

    def finish(cancelled: bool) -> None:
        summary["cancelled"] = cancelled
        emit("done", summary)

    try:
        pdf_paths, skipped_folders = discover_pdfs(
            root_path, cancel_event,
            lambda found, folders, skipped: emit("discovering", (found, folders, skipped)),
        )
        summary["skipped_dirs"] = len(skipped_folders)
        summary["skipped_folders"] = skipped_folders
        if cancel_event.is_set():
            return finish(True)
        total = len(pdf_paths)
        emit("scan_total", total)
        if total == 0:
            return finish(False)

        inspected: dict[str, dict[str, Any]] = {}
        size_groups: dict[int, list[str]] = defaultdict(list)

        def on_inspected(path: Path, record: dict[str, Any] | None, error: BaseException | None) -> None:
            if record is None:
                record = failed_record(path, str(error) or type(error).__name__)
            inspected[record["path"]] = record
            if record["size_bytes"] is not None:
                size_groups[record["size_bytes"]].append(record["path"])
            emit("file", dict(record))
            emit("inspect_progress", (len(inspected), total))

        if not bounded_map(inspect_pdf, pdf_paths, cancel_event, on_inspected,
                           timeout=INSPECT_TIMEOUT_SECONDS, name="PDFInspect", governor=governor):
            return finish(True)

        # Hard links share one file: hash only the first path and give the others its result.
        hard_link_of: dict[str, str] = {}
        candidates: list[dict[str, Any]] = []
        for group in size_groups.values():
            first_path_by_id: dict[Any, str] = {}
            distinct: list[dict[str, Any]] = []
            # Inspection finishes in thread order; sort so the same link is "first" on every run.
            for path in sorted(group, key=str.casefold):
                record = inspected[path]
                file_id = record["file_id"]
                if file_id is not None and file_id in first_path_by_id:
                    hard_link_of[path] = first_path_by_id[file_id]
                    continue
                if file_id is not None:
                    first_path_by_id[file_id] = path
                distinct.append(record)
            if len(distinct) > 1:
                for record in distinct:
                    record["duplicate"] = None
                    candidates.append(record)
                    emit("file_update", dict(record))

        # Stage 1: a small partial hash narrows same-size files to likely matches.
        quick_results: dict[str, str | None] = {}
        if candidates:
            emit("hash_stage", ("quick", len(candidates)))

            def on_quick(record: dict[str, Any], value: str | None, error: BaseException | None) -> None:
                quick_results[record["path"]] = None if error else value
                emit("hash_progress", ("quick", len(quick_results), len(candidates)))

            if not bounded_map(lambda rec: _quick_hash(Path(rec["path"]), rec["size_bytes"], rec["mtime_ns"]),
                               candidates, cancel_event, on_quick, name="PDFQuickHash", governor=governor):
                return finish(True)

        likely_groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        for record in candidates:
            quick = quick_results.get(record["path"])
            if quick:
                likely_groups[(record["size_bytes"], quick)].append(record)
        full_candidates = [rec for group in likely_groups.values() if len(group) > 1 for rec in group]

        # Same-size files with different partial hashes are definitely not duplicates.
        states: dict[str, bool | None] = {
            rec["path"]: False if quick_results.get(rec["path"]) else None for rec in candidates
        }
        groups: dict[str, int] = {}
        if full_candidates:
            emit("hash_stage", ("full", len(full_candidates)))
            full_results: dict[str, str | None] = {}

            def on_full(record: dict[str, Any], value: str | None, error: BaseException | None) -> None:
                full_results[record["path"]] = None if error else value
                emit("hash_progress", ("full", len(full_results), len(full_candidates)))

            if not bounded_map(
                lambda rec: _full_hash(Path(rec["path"]), rec["size_bytes"], rec["mtime_ns"], cancel_event,
                                       governor.profile.hash_chunk),
                full_candidates, cancel_event, on_full, name="PDFFullHash", governor=governor,
            ):
                return finish(True)

            digest_groups: dict[str, list[str]] = defaultdict(list)
            for path, digest in full_results.items():
                if digest:
                    digest_groups[digest].append(path)
                else:
                    states[path] = None
            # Number groups by their first path so the same library gets the same group numbers.
            matched = sorted((sorted(paths, key=str.casefold) for paths in digest_groups.values() if len(paths) > 1),
                             key=lambda paths: paths[0].casefold())
            for number, paths in enumerate(matched, start=1):
                for path in paths:
                    states[path] = True
                    groups[path] = number

        for path, first_path in hard_link_of.items():
            # Report every name of a hard-linked file, including the first one.
            states.setdefault(first_path, False)
            states[path] = states[first_path]
            if first_path in groups:
                groups[path] = groups[first_path]
        emit("duplicates", {"states": states, "groups": groups})
        finish(cancel_event.is_set())
    except Exception as exc:
        logging.exception("Unexpected scanner failure")
        summary["error"] = str(exc)
        finish(cancel_event.is_set())


# ---------- Filename cleaner ----------
# Source tags that download sites append to PDF names. Only an exact tag at the very end of the
# name is removed, so "Book (Z-Library)_compressed.pdf" is left alone.
CLEANER_MARKER_SUFFIX = re.compile(
    r"\s*\((?P<marker>z-library|z-library\.sk\s*,\s*1lib\.sk\s*,\s*z-lib\.sk)\)\s*$",
    re.IGNORECASE,
)
RENAME_REPORT_HEADERS = ("Status", "Marker", "Source", "Destination", "Detail")


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
    match = CLEANER_MARKER_SUFFIX.search(path.stem)
    if not match:
        return None
    cleaned_stem = CLEANER_MARKER_SUFFIX.sub("", path.stem).rstrip()
    if not cleaned_stem:
        return None
    return cleaned_stem + path.suffix, match.group("marker")


def plan_renames(pdf_paths: Iterable[Path]) -> list[RenamePlan]:
    """Build a collision-safe rename preview for the supplied PDF paths."""
    plans: list[RenamePlan] = []
    for source in pdf_paths:
        cleaned = cleaned_pdf_name(source.name)
        if cleaned:
            name, marker = cleaned
            plans.append(RenamePlan(source, source.with_name(name), marker, "ready", "Ready to rename"))

    by_destination: dict[str, int] = defaultdict(int)
    for plan in plans:
        by_destination[str(plan.destination).casefold()] += 1
    return [
        replace(plan, status="collision", detail="Another matched file has the same cleaned name")
        if by_destination[str(plan.destination).casefold()] > 1 else plan
        for plan in plans
    ]


def preflight_renames(plans: Iterable[RenamePlan]) -> list[RenamePlan]:
    """Re-check ready plans against the disk so a preview shows what applying would do."""
    checked: list[RenamePlan] = []
    for plan in plans:
        if plan.status == "ready" and plan.destination is not None:
            if not plan.source.is_file():
                plan = replace(plan, status="skipped", detail="Source file is no longer available")
            elif plan.destination.exists():
                plan = replace(plan, status="collision", detail="A file with the new name already exists")
        checked.append(plan)
    return checked


def _move_without_overwrite(source: Path, destination: Path) -> None:
    """Rename without replacing an existing destination or modifying file content."""
    if os.name == "nt":
        import ctypes

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


def apply_renames(plans: Iterable[RenamePlan],
                  on_outcome: Callable[[RenamePlan], None] | None = None) -> list[RenamePlan]:
    """Apply only ready plans and record all results without overwriting files."""
    outcomes: list[RenamePlan] = []
    for plan in preflight_renames(plans):
        if plan.status == "ready" and plan.destination is not None:
            try:
                _move_without_overwrite(plan.source, plan.destination)
            except FileExistsError:
                plan = replace(plan, status="collision", detail="A file with the new name already exists")
            except OSError as exc:
                plan = replace(plan, status="error", detail=str(exc))
            else:
                plan = replace(plan, status="renamed", detail="Renamed safely")
        outcomes.append(plan)
        if on_outcome is not None:
            on_outcome(plan)
    return outcomes


def _report_row(plan: RenamePlan) -> tuple[str, str, str, str, str]:
    return plan.status, plan.marker or "", str(plan.source), str(plan.destination or ""), plan.detail


def write_rename_report(destination: Path, plans: Iterable[RenamePlan]) -> None:
    """Write an audit report that load_undo_plans can read back."""
    write_csv_export(destination, RENAME_REPORT_HEADERS, (_report_row(plan) for plan in plans), ",")


def default_report_path(directory: Path, prefix: str) -> Path:
    """Return an unused, timestamped report path inside directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for index in range(1, 10_000):
        suffix = "" if index == 1 else f"_{index}"
        candidate = directory / f"{prefix}_{timestamp}{suffix}.csv"
        if not candidate.exists():
            return candidate
    raise OSError("Could not allocate a unique report filename")


def run_renames(plans: Sequence[RenamePlan], report_path: Path) -> tuple[list[RenamePlan], OSError | None]:
    """Apply plans and record every outcome in report_path.

    Raises OSError before renaming anything when the report cannot be created. Each outcome is
    appended to the report as it happens, so a crash mid-run still leaves an undo record; the
    complete report then replaces it. If the final report cannot be written, the renamed pairs
    are logged and the error is returned.
    """
    write_rename_report(report_path, [])
    journal_error: OSError | None = None
    with report_path.open("a", encoding="utf-8", newline="") as journal:
        writer = csv.writer(journal, lineterminator="\r\n")

        def journal_outcome(plan: RenamePlan) -> None:
            nonlocal journal_error
            if journal_error is None:
                try:
                    writer.writerow([sanitize_csv_cell(value) for value in _report_row(plan)])
                    journal.flush()
                except OSError as exc:  # The final report below is still attempted.
                    journal_error = exc

        outcomes = apply_renames(plans, journal_outcome)
    try:
        write_rename_report(report_path, outcomes)
    except OSError as exc:
        for plan in outcomes:
            if plan.status == "renamed":
                logging.error("Renamed without a saved report: %s -> %s", plan.source, plan.destination)
        return outcomes, exc
    return outcomes, None


def load_undo_plans(report_path: Path) -> tuple[list[RenamePlan], list[str]]:
    """Load only validated completed renames from a cleanup report."""
    plans: list[RenamePlan] = []
    warnings: list[str] = []
    try:
        with report_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not set(RENAME_REPORT_HEADERS).issubset(reader.fieldnames):
                return [], ["The report does not have the expected cleanup columns."]
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


# ---------- Application files, logging and window placement ----------
DATA_DIR_NAME = "pdf_inventory_data"


def program_dir() -> Path:
    """Folder that contains the program: the script, or the executable when packaged."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def app_data_dir() -> Path:
    """Portable folder next to the program for settings, rename reports and the log file.

    Nothing is written to per-user locations such as %APPDATA%, so each copy of the program
    keeps its own data and can be moved together with it.
    """
    return program_dir() / DATA_DIR_NAME


def log_file_path() -> Path:
    return app_data_dir() / "pdf_inventory.log"


def configure_logging() -> None:
    """Log warnings and errors to stderr (when there is one) and to a small rotating file."""
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    try:
        log_file_path().parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file_path(), maxBytes=512 * 1024, backupCount=1, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.WARNING, handlers=handlers,
                        format="%(asctime)s %(levelname)s [%(threadName)s] %(message)s")


def virtual_screen_bounds(root: tk.Misc) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of the desktop across all monitors."""
    if sys.platform == "win32":
        try:
            import ctypes

            metrics = ctypes.windll.user32.GetSystemMetrics  # type: ignore[attr-defined]
            left, top, width, height = metrics(76), metrics(77), metrics(78), metrics(79)  # SM_*VIRTUALSCREEN
            if width > 0 and height > 0:
                return left, top, left + width, top + height
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def geometry_is_visible(geometry: str, screen: tuple[int, int, int, int]) -> bool:
    """True when a saved WxH+X+Y geometry fits the screen and its title bar can be reached."""
    match = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geometry)
    if not match:
        return False
    width, height, x, y = map(int, match.groups())
    left, top, right, bottom = screen
    grab_x, grab_y = x + min(width, 120) // 2, y + 10
    return (width <= right - left and height <= bottom - top
            and left <= grab_x < right and top <= grab_y < bottom)


AUTHOR_URL = "https://keremaydin.net"


def one_line(text: str, limit: int = 300) -> str:
    """Collapse whitespace so multi-line parser errors fit in one table cell."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit - 1] + "…"


# Dark theme palette shared by the main window, dialogs, menus and icons.
COLORS = {
    "window": "#17191d", "bg": "#202329", "panel": "#252a31", "field": "#171b21",
    "table": "#1b1f25", "table_alt": "#20252c", "heading": "#2b313a", "heading_hover": "#36404c",
    "border": "#3a414b", "button": "#343b45", "button_hover": "#414955", "button_disabled": "#2b3037",
    "accent": "#2563eb", "accent_hover": "#1d4ed8", "danger": "#b42318", "danger_hover": "#912018",
    "select": "#244d78", "text": "#e5e7eb", "text_strong": "#f3f4f6", "muted": "#a7b0bd",
    "faint": "#7f8a99", "disabled": "#7b828c", "white": "#ffffff", "tooltip": "#2f353e",
    "error": "#ff7777", "warning": "#f0be67", "unreadable": "#ff9999", "pdf": "#e5484d",
}

# Icons are drawn on a 24-unit grid with a 2-unit stroke, then rasterised at the display scale so they
# stay sharp at any DPI without image files. Shape kinds: "line" (polyline), "ring" (circle outline),
# "arc" (cx, cy, r, start, end in degrees clockwise from +x) and "box" (rounded-rectangle outline) are
# stroked; "disc", "poly" (points, corner rounding) and "fbox" are filled. An optional third item
# paints the shape in that colour instead of the icon colour.
ICONS: dict[str, list[tuple[Any, ...]]] = {
    "folder": [("line", ((3, 19), (3, 5), (9, 5), (11, 7), (21, 7), (21, 19), (3, 19)))],
    "play": [("poly", (((8, 5.5), (18.5, 12), (8, 18.5)), 1.5))],
    "stop": [("fbox", (6.5, 6.5, 17.5, 17.5, 2))],
    "gauge": [("arc", (12, 14, 9, 150, 390)), ("line", ((12, 14), (16, 9))), ("disc", (12, 14, 1.8))],
    "gear": [("line", tuple(
        (12 + radius * math.cos(math.radians(tooth * 45 + offset)),
         12 + radius * math.sin(math.radians(tooth * 45 + offset)))
        for tooth in range(8) for offset, radius in ((-22.5, 7.2), (-12, 7.2), (-8, 10), (8, 10), (12, 7.2))
    ) + ((12 + 7.2 * math.cos(math.radians(-22.5)), 12 + 7.2 * math.sin(math.radians(-22.5))),)),
             ("ring", (12, 12, 3))],
    "search": [("ring", (10.5, 10.5, 6.5)), ("line", ((15.5, 15.5), (20.5, 20.5)))],
    "close": [("line", ((7.5, 7.5), (16.5, 16.5))), ("line", ((16.5, 7.5), (7.5, 16.5)))],
    "eraser": [("line", ((4, 15), (13, 6), (19.5, 12.5), (11, 21), (8, 21), (4, 17), (4, 15))),
               ("line", ((8.5, 10.5), (15, 17))), ("line", ((11, 21), (21, 21)))],
    "undo": [("line", ((9, 14), (4, 9), (9, 4))), ("line", ((4, 9), (14.5, 9))),
             ("arc", (14.5, 14.5, 5.5, -90, 90)), ("line", ((14.5, 20), (11, 20)))],
    "export": [("line", ((12, 21), (5, 21), (5, 3), (13, 3), (17, 7), (17, 10))),
               ("line", ((13, 3), (13, 7), (17, 7))), ("line", ((10, 15.5), (21, 15.5))),
               ("line", ((17.5, 12), (21, 15.5), (17.5, 19)))],
    "warning": [("line", ((12, 3.5), (21.5, 20), (2.5, 20), (12, 3.5))), ("line", ((12, 9.5), (12, 13.5))),
                ("disc", (12, 16.8, 1.3))],
    "app": [("poly", (((5, 2.5), (14.5, 2.5), (20, 8), (20, 21.5), (5, 21.5)), 1), COLORS["pdf"]),
            ("poly", (((14.5, 2.5), (14.5, 8), (20, 8)), 0.5), "#ffb3b5"),
            ("fbox", (8, 11.5, 17, 13, 0.75), COLORS["white"]),
            ("fbox", (8, 14.75, 17, 16.25, 0.75), COLORS["white"]),
            ("fbox", (8, 18, 13.5, 19.5, 0.75), COLORS["white"])],
}
STROKED_SHAPES = {"line", "ring", "arc", "box"}


def _segment_distance(x: float, y: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / length))
    return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)


def _shape_distance(kind: str, params: Any, x: float, y: float) -> float:
    """Distance in grid units from (x, y) to a stroked shape, or signed distance to a filled one."""
    if kind == "line":
        return min(_segment_distance(x, y, a, b) for a, b in zip(params, params[1:]))
    if kind in {"ring", "disc"}:
        cx, cy, radius = params
        distance = math.hypot(x - cx, y - cy) - radius
        return abs(distance) if kind == "ring" else distance
    if kind == "arc":
        cx, cy, radius, start, end = params
        if (math.degrees(math.atan2(y - cy, x - cx)) - start) % 360 <= end - start:
            return abs(math.hypot(x - cx, y - cy) - radius)
        return min(math.hypot(x - cx - radius * math.cos(math.radians(a)), y - cy - radius * math.sin(math.radians(a)))
                   for a in (start, end))
    if kind in {"box", "fbox"}:
        x0, y0, x1, y1, radius = params
        qx = abs(x - (x0 + x1) / 2) - ((x1 - x0) / 2 - radius)
        qy = abs(y - (y0 + y1) / 2) - ((y1 - y0) / 2 - radius)
        distance = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - radius
        return abs(distance) if kind == "box" else distance
    points, rounding = params
    edges = list(zip(points, points[1:] + points[:1]))
    distance = min(_segment_distance(x, y, a, b) for a, b in edges)
    inside = False
    for (ax, ay), (bx, by) in edges:
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return (-distance if inside else distance) - rounding


def render_icon_png(shapes: Sequence[tuple[Any, ...]], size: int, color: str, gap: int = 0) -> bytes:
    """Rasterise an icon to an anti-aliased RGBA PNG, with `gap` transparent columns on the right."""
    scale = size / 24
    raw = bytearray()
    for row in range(size):
        raw.append(0)  # PNG filter type: none.
        y = (row + 0.5) / scale
        for column in range(size):
            x = (column + 0.5) / scale
            red = green = blue = alpha = 0.0  # Premultiplied.
            for shape in shapes:
                distance = _shape_distance(shape[0], shape[1], x, y) * scale
                # A 2-unit stroke reaches `scale` pixels either side of the centre line.
                edge = scale - abs(distance) if shape[0] in STROKED_SHAPES else -distance
                coverage = max(0.0, min(1.0, edge + 0.5))
                if coverage:
                    paint = shape[2] if len(shape) > 2 else color
                    r, g, b = int(paint[1:3], 16), int(paint[3:5], 16), int(paint[5:7], 16)
                    keep = 1.0 - coverage
                    red, green, blue = r * coverage + red * keep, g * coverage + green * keep, b * coverage + blue * keep
                    alpha = coverage + alpha * keep
            if alpha:
                raw += bytes((round(red / alpha), round(green / alpha), round(blue / alpha), round(alpha * 255)))
            else:
                raw += b"\0\0\0\0"
        raw += b"\0\0\0\0" * gap

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size + gap, size, 8, 6, 0, 0, 0)  # 8-bit RGBA.
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


@lru_cache(maxsize=None)
def icon_png(name: str, size: int, color: str, gap: int = 0) -> bytes:
    """Cached so windows opened later in the same process, such as in tests, skip rasterising."""
    return render_icon_png(ICONS[name], size, color, gap)


class Tooltip:
    """Show a short hint below a widget once the pointer rests on it."""

    DELAY_MS = 550

    def __init__(self, widget: tk.Misc, text: Callable[[], str]):
        self.widget = widget
        self.text = text  # Called on every show, so a language change is picked up.
        self._job: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: Any = None) -> None:
        self._hide()
        self._job = self.widget.after(self.DELAY_MS, self._show)

    def _show(self) -> None:
        self._job = None
        text = self.text()
        if not text or not self.widget.winfo_viewable():
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_attributes("-topmost", True)
        tk.Label(tip, text=text, bg=COLORS["tooltip"], fg=COLORS["text_strong"], font=("Segoe UI", 9),
                 padx=8, pady=4, highlightthickness=1, highlightbackground=COLORS["border"]).pack()
        tip.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - tip.winfo_reqwidth() - 4)
        tip.wm_geometry(f"+{max(0, x)}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 4}")
        self._tip = tip

    def _hide(self, _event: Any = None) -> None:
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class PDFInventoryApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings_path = self._settings_path()
        self.reports_dir = self.settings_path.parent / "rename_reports"
        self.settings = self._load_settings()
        saved_lang = self.settings.get("language")
        self.current_lang = saved_lang if saved_lang in TRANSLATIONS else self._get_system_language()
        # Every launch starts in the folder the program is in, so copying it into a library and
        # starting it there scans that library. Browse… changes the folder for this session only.
        self.target_directory = str(program_dir())
        self.csv_separator = self.settings.get("csv_separator", "auto")
        if self.csv_separator not in CSV_SEPARATORS:
            self.csv_separator = "auto"
        self.last_export_dir = self.settings.get("last_export_dir", self.target_directory)
        # Records stay in arrival order; the unsorted table shows them in this order.
        self.records: dict[str, dict[str, Any]] = {}
        # Normalized (search text, name, folder, path) per record, rebuilt when a record changes.
        self._search_keys: dict[str, tuple[str, str, str, str]] = {}
        self._iid_by_path: dict[str, str] = {}
        self._path_by_iid: dict[str, str] = {}
        self._row_stripe: dict[str, str] = {}
        self._pending_render_paths: list[str] = []
        self._pending_render_set: set[str] = set()
        self._table_mode: tuple[str, str | None, bool, bool] | None = None
        self._visible_paths: list[str] = []
        self._last_full_refresh = 0.0
        self._refresh_pending = False
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=MAX_UI_QUEUE_EVENTS)
        self._cancel_event = threading.Event()
        self._scan_thread: threading.Thread | None = None
        self.is_scanning = False
        self._closing = False
        self._search_after_id: str | None = None
        self._last_status: tuple[str, dict[str, Any]] = ("status_ready", {})
        self._skipped_dirs = 0
        self._skipped_folders: list[tuple[str, str]] = []
        self._rename_dialog: tk.Toplevel | None = None
        self._sort_column: str | None = None
        self._sort_reverse = False
        self.duplicates_only_var = tk.BooleanVar(value=False)
        self._ui_scale = 1.0
        # Not saved: every launch starts at the default level, whatever the last session used.
        self.resource_governor = ResourceGovernor()
        self.resource_level_var = tk.StringVar(value=self.resource_governor.level)
        self._resource_notice: tuple[str, dict[str, Any]] | None = None
        self._resource_notice_until = 0.0
        self._resource_notice_job: str | None = None
        self.language_var = tk.StringVar(value=self.current_lang)
        self.separator_var = tk.StringVar(value=self.csv_separator)
        self._has_scanned = False
        # PhotoImages vanish when Python drops the last reference, so the app keeps every icon here.
        self._images: dict[tuple[str, int, str, int], tk.PhotoImage] = {}

        self._setup_window()
        self._setup_styles()
        self._setup_menu()
        self._setup_ui()
        self._update_language()
        self._set_status("status_ready")
        self.root.after(100, self._poll_worker_queue)

    # ---------- Paths and settings ----------
    @staticmethod
    def _settings_path() -> Path:
        return app_data_dir() / "settings.json"

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

    def _photo(self, name: str, size: int, color: str, gap: int = 0) -> tk.PhotoImage:
        key = (name, size, color, gap)
        image = self._images.get(key)
        if image is None:
            data = base64.b64encode(icon_png(name, size, color, gap)).decode("ascii")
            image = self._images[key] = tk.PhotoImage(master=self.root, data=data)
        return image

    def _icon(self, name: str, color: str = COLORS["text"], label: bool = True) -> tuple[Any, ...]:
        """Image option for a ttk button: the icon in `color`, greyed out while the button is disabled.

        Icons beside a label get a transparent gap on the right, since ttk puts no space between them.
        """
        size, gap = self._px(16), self._px(6) if label else 0
        return (self._photo(name, size, color, gap), "disabled", self._photo(name, size, COLORS["disabled"], gap))

    # ---------- Window, style and interface ----------
    def _setup_window(self) -> None:
        self.root.update_idletasks()
        try:
            self._ui_scale = max(0.85, min(2.0, self.root.winfo_fpixels("1i") / 96.0))
        except tk.TclError:
            self._ui_scale = 1.0
        width, height = self._px(1180), self._px(760)
        self.root.minsize(self._px(900), self._px(520))
        geometry = self.settings.get("geometry")
        # A saved position can be off-screen after a monitor is disconnected or rearranged.
        if isinstance(geometry, str) and geometry_is_visible(geometry, virtual_screen_bounds(self.root)):
            self.root.geometry(geometry)
        else:
            x = max(0, (self.root.winfo_screenwidth() - width) // 2)
            y = max(0, (self.root.winfo_screenheight() - height) // 2)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.configure(bg=COLORS["window"])
        # The window and taskbar icon; True makes dialogs inherit it.
        self.root.iconphoto(True, *(self._photo("app", size, COLORS["pdf"]) for size in (16, 32, 64)))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self) -> None:
        c = COLORS
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        font, strong = ("Segoe UI", 9), ("Segoe UI Semibold", 9)
        style.configure(".", background=c["bg"], foreground=c["text"], bordercolor=c["border"],
                        troughcolor=c["field"], focuscolor=c["accent"], font=font)
        style.configure("TFrame", background=c["bg"])
        style.configure("Panel.TFrame", background=c["panel"])
        style.configure("TLabel", background=c["panel"], foreground=c["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=c["panel"], foreground=c["muted"], font=font)
        style.configure("Count.TLabel", background=c["panel"], foreground=c["muted"], font=font)
        style.configure("Credit.TLabel", background=c["bg"], foreground=c["faint"], font=("Segoe UI", 8))
        style.configure("Icon.TLabel", background=c["panel"])
        style.configure("Empty.TLabel", background=c["table"], foreground=c["faint"], font=("Segoe UI", 11))
        style.configure("TSeparator", background=c["border"])
        style.configure("TEntry", fieldbackground=c["field"], foreground=c["text_strong"], insertcolor=c["white"],
                        bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"], padding=self._px(6))
        style.map("TEntry", fieldbackground=[("disabled", c["panel"])], foreground=[("disabled", c["disabled"])])
        # The search entry sits inside a frame that draws the border and the focus ring for it.
        style.configure("Bare.TEntry", bordercolor=c["field"], lightcolor=c["field"], darkcolor=c["field"],
                        padding=(self._px(2), self._px(6)))
        style.configure("TCombobox", fieldbackground=c["field"], background=c["button"], foreground=c["text_strong"],
                        arrowcolor=c["text"], bordercolor=c["border"], lightcolor=c["field"], darkcolor=c["field"],
                        arrowsize=self._px(12), padding=(self._px(6), self._px(7)))
        style.map("TCombobox", fieldbackground=[("readonly", c["field"])], foreground=[("readonly", c["text_strong"])],
                  background=[("pressed", c["button_hover"]), ("active", c["button_hover"])],
                  bordercolor=[("focus", c["accent"])],
                  selectbackground=[("readonly", c["field"])], selectforeground=[("readonly", c["text_strong"])])
        for option, value in (("background", c["field"]), ("foreground", c["text_strong"]),
                              ("selectBackground", c["accent"]), ("selectForeground", c["white"])):
            self.root.option_add(f"*TCombobox*Listbox.{option}", value)
        style.configure("TCheckbutton", background=c["bg"], foreground=c["text"], indicatorbackground=c["field"],
                        indicatorforeground=c["white"], upperbordercolor=c["border"], lowerbordercolor=c["border"],
                        indicatorsize=self._px(14), indicatormargin=(0, 0, self._px(6), 0))
        style.map("TCheckbutton", background=[("active", c["bg"])], foreground=[("disabled", c["disabled"])],
                  indicatorbackground=[("selected", c["accent"]), ("pressed", c["button"])])
        style.configure("Treeview", background=c["table"], fieldbackground=c["table"], foreground=c["text"],
                        bordercolor=c["border"], lightcolor=c["table"], darkcolor=c["table"],
                        rowheight=self._px(29), borderwidth=0, font=font)
        style.map("Treeview", background=[("selected", c["select"])], foreground=[("selected", c["white"])])
        style.configure("Treeview.Heading", background=c["heading"], foreground=c["text_strong"], relief="flat",
                        bordercolor=c["border"], lightcolor=c["heading"], darkcolor=c["heading"],
                        font=strong, padding=(self._px(2), self._px(7)))  # Lines headings up with cell text.
        style.map("Treeview.Heading", background=[("active", c["heading_hover"])])
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar", background=c["button"], troughcolor=c["table"],
                            bordercolor=c["table"], lightcolor=c["button"], darkcolor=c["button"],
                            arrowcolor=c["muted"], gripcount=0, arrowsize=self._px(12))
            style.map(f"{orient}.TScrollbar", background=[("active", c["button_hover"])],
                      lightcolor=[("active", c["button_hover"])], darkcolor=[("active", c["button_hover"])])
        # Only the scan button is filled with the accent colour; every other action is a quiet secondary button.
        for name, color, hover, text, weight in (
            ("Accent", c["accent"], c["accent_hover"], c["white"], strong),
            ("Danger", c["danger"], c["danger_hover"], c["white"], strong),
            ("Neutral", c["button"], c["button_hover"], c["text_strong"], font),
        ):
            style.configure(f"{name}.TButton", background=color, foreground=text, borderwidth=1, bordercolor=color,
                            lightcolor=color, darkcolor=color, focusthickness=0, focuscolor=color,
                            padding=(self._px(12), self._px(6)), font=weight)
            states = [("disabled", c["button_disabled"]), ("pressed", hover), ("active", hover)]
            style.map(f"{name}.TButton", background=states, bordercolor=states, lightcolor=states, darkcolor=states,
                      foreground=[("disabled", c["disabled"])])
        style.configure("Icon.Neutral.TButton", padding=(self._px(7), self._px(6)))
        style.configure("Link.TButton", background=c["panel"], foreground=c["warning"], borderwidth=0,
                        bordercolor=c["panel"], lightcolor=c["panel"], darkcolor=c["panel"], focusthickness=0,
                        focuscolor=c["panel"], padding=(self._px(6), self._px(2)), font=font)
        style.map("Link.TButton", background=[("active", c["button"])], lightcolor=[("active", c["button"])],
                  darkcolor=[("active", c["button"])], bordercolor=[("active", c["button"])])
        style.configure("TProgressbar", troughcolor=c["field"], background=c["accent"], bordercolor=c["field"],
                        lightcolor=c["accent"], darkcolor=c["accent"], thickness=self._px(6))

    @staticmethod
    def _popup_menu_colors() -> dict[str, str]:
        return {"bg": COLORS["panel"], "fg": COLORS["text_strong"], "activebackground": COLORS["accent"],
                "activeforeground": COLORS["white"], "selectcolor": COLORS["text_strong"]}

    def _setup_menu(self) -> None:
        # Labels are set in _update_language; entry indices below are referenced there.
        self.menubar = tk.Menu(self.root, tearoff=False)
        self.file_menu = tk.Menu(self.menubar, tearoff=False)
        self.file_menu.add_command(command=self._select_folder, accelerator="Ctrl+O")
        self.file_menu.add_command(command=self._start_scan, accelerator="Ctrl+R")
        self.file_menu.add_command(command=self._export_csv, accelerator="Ctrl+E")
        self.file_menu.add_separator()
        self.file_menu.add_command(command=self._on_close)
        self.tools_menu = tk.Menu(self.menubar, tearoff=False)
        self.tools_menu.add_command(command=self._open_filename_cleaner)
        self.tools_menu.add_command(command=self._open_cleanup_undo)
        self.tools_menu.add_separator()
        self.resources_menu = tk.Menu(self.tools_menu, tearoff=False)
        self.resources_menu.add_command(state=tk.DISABLED)
        self.resources_menu.add_separator()
        for level in RESOURCE_LEVELS:
            self.resources_menu.add_radiobutton(variable=self.resource_level_var, value=level,
                                                command=self._on_resource_level_change)
        self.tools_menu.add_cascade(menu=self.resources_menu)
        self.tools_menu.add_separator()
        # The gear button in the command bar opens the same Language and CSV separator choices.
        self.settings_menu = tk.Menu(self.root, tearoff=False, **self._popup_menu_colors())
        self._settings_menus = [self._add_settings_entries(self.tools_menu, {}),
                                self._add_settings_entries(self.settings_menu, self._popup_menu_colors())]
        self.help_menu = tk.Menu(self.menubar, tearoff=False)
        self.help_menu.add_command(command=self._show_about)
        self.help_menu.add_command(command=lambda: webbrowser.open(AUTHOR_URL))
        self.menubar.add_cascade(menu=self.file_menu)
        self.menubar.add_cascade(menu=self.tools_menu)
        self.menubar.add_cascade(menu=self.help_menu)
        self.root.configure(menu=self.menubar)

    def _add_settings_entries(self, menu: tk.Menu, colors: dict[str, str]) -> tuple[tk.Menu, int, tk.Menu]:
        """Append Language and CSV separator submenus; return (menu, first entry index, separator submenu)."""
        language_menu = tk.Menu(menu, tearoff=False, **colors)
        for code, name in LANGUAGE_NAMES.items():
            language_menu.add_radiobutton(label=name, variable=self.language_var, value=code,
                                          command=self._on_language_change)
        separator_menu = tk.Menu(menu, tearoff=False, **colors)
        for key in CSV_SEPARATORS:
            separator_menu.add_radiobutton(variable=self.separator_var, value=key, command=self._on_separator_change)
        last = menu.index(tk.END)
        menu.add_cascade(menu=language_menu)
        menu.add_cascade(menu=separator_menu)
        return menu, 0 if last is None else last + 1, separator_menu

    def _setup_ui(self) -> None:
        # Command bar: the scan task reads left to right (where, how hard, go), then the settings gear.
        self.top_frame = ttk.Frame(self.root, style="Panel.TFrame", padding=(self._px(16), self._px(12)))
        self.top_frame.pack(fill=tk.X)
        self.lbl_target = ttk.Label(self.top_frame, style="Muted.TLabel")
        self.lbl_target.pack(side=tk.LEFT, padx=(0, self._px(10)))
        self.btn_settings = ttk.Button(self.top_frame, style="Icon.Neutral.TButton",
                                       image=self._icon("gear", label=False), command=self._show_settings_menu)
        self.btn_settings.pack(side=tk.RIGHT, padx=(self._px(8), 0))
        self.btn_scan = ttk.Button(self.top_frame, style="Accent.TButton", compound=tk.LEFT, command=self._start_scan)
        self.btn_scan.pack(side=tk.RIGHT)
        self.resource_combo = ttk.Combobox(self.top_frame, state="readonly", width=20)
        self.resource_combo.pack(side=tk.RIGHT, padx=(0, self._px(8)))
        self.resource_combo.bind("<<ComboboxSelected>>", self._on_resource_combo_change)
        self.lbl_resources = ttk.Label(self.top_frame, style="Icon.TLabel",
                                       image=self._photo("gauge", self._px(16), COLORS["muted"]))
        self.lbl_resources.pack(side=tk.RIGHT, padx=(0, self._px(6)))
        ttk.Separator(self.top_frame, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=self._px(12),
                                                               pady=self._px(4))
        self.btn_browse = ttk.Button(self.top_frame, style="Neutral.TButton", image=self._icon("folder"),
                                     compound=tk.LEFT, command=self._select_folder)
        self.btn_browse.pack(side=tk.RIGHT)
        self.path_var = tk.StringVar(value=self.target_directory)
        self.path_entry = ttk.Entry(self.top_frame, textvariable=self.path_var, state="readonly")
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, self._px(8)))

        # View bar: decides which rows are visible and holds the actions that work on exactly those rows.
        view_bar = ttk.Frame(self.root, style="TFrame", padding=(self._px(16), self._px(10)))
        view_bar.pack(fill=tk.X)
        self.search_box = tk.Frame(view_bar, bg=COLORS["field"], highlightthickness=1,
                                   highlightbackground=COLORS["border"], highlightcolor=COLORS["border"])
        self.search_box.pack(side=tk.LEFT)
        tk.Label(self.search_box, image=self._photo("search", self._px(16), COLORS["faint"]),
                 bg=COLORS["field"]).pack(side=tk.LEFT, padx=(self._px(8), 0))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.search_box, textvariable=self.search_var, width=34, style="Bare.TEntry")
        self.search_entry.pack(side=tk.LEFT, padx=(self._px(2), 0))
        self.search_var.trace_add("write", self._on_search_changed)
        for sequence, color in (("<FocusIn>", COLORS["accent"]), ("<FocusOut>", COLORS["border"])):
            self.search_entry.bind(sequence, lambda _e, c=color: self.search_box.configure(highlightbackground=c),
                                   add="+")
        self.search_placeholder = tk.Label(self.search_box, bg=COLORS["field"], fg=COLORS["faint"],
                                           font=("Segoe UI", 9), cursor="xterm")
        self.search_placeholder.bind("<Button-1>", lambda _e: self.search_entry.focus_set())
        clear_size = self._px(14)
        self._clear_icons = (self._photo("close", clear_size, COLORS["muted"]),
                             tk.PhotoImage(master=self.root, width=clear_size, height=clear_size))
        # Always packed so the box keeps its width; it shows a blank image while there is nothing to clear.
        self.btn_clear = tk.Label(self.search_box, bg=COLORS["field"], image=self._clear_icons[1])
        self.btn_clear.pack(side=tk.LEFT, padx=(self._px(2), self._px(8)))
        self.btn_clear.bind("<Button-1>", lambda _e: self._clear_search())
        self.duplicates_only = ttk.Checkbutton(
            view_bar, variable=self.duplicates_only_var, command=self._on_filter_changed,
        )
        self.duplicates_only.pack(side=tk.LEFT, padx=(self._px(14), 0))
        self.btn_export = ttk.Button(view_bar, style="Neutral.TButton", image=self._icon("export"), compound=tk.LEFT,
                                     command=self._export_csv, state=tk.DISABLED)
        self.btn_export.pack(side=tk.RIGHT)
        self.btn_undo = ttk.Button(view_bar, style="Icon.Neutral.TButton", image=self._icon("undo", label=False),
                                   command=self._open_cleanup_undo)
        self.btn_undo.pack(side=tk.RIGHT, padx=(0, self._px(12)))
        self.btn_clean = ttk.Button(view_bar, style="Neutral.TButton", image=self._icon("eraser"), compound=tk.LEFT,
                                    command=self._open_filename_cleaner)
        self.btn_clean.pack(side=tk.RIGHT, padx=(0, self._px(2)))

        table_frame = ttk.Frame(self.root, style="TFrame", padding=(self._px(16), 0, self._px(16), self._px(10)))
        table_frame.pack(fill=tk.BOTH, expand=True)
        # Problem sits before the wide path column so a corruption reason is visible without scrolling.
        self.columns = ("name", "folder", "size", "pages", "date", "duplicate", "problem", "path")
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings", selectmode="extended")
        widths = {"name": 235, "folder": 150, "size": 92, "pages": 76, "date": 142, "duplicate": 130,
                  "problem": 200, "path": 390}
        for column in self.columns:
            # Numbers align right so their digits line up, and the fixed-width date is centred so it keeps
            # clear of the page counts; headings follow their column.
            anchor = tk.E if column in {"size", "pages"} else tk.CENTER if column == "date" else tk.W
            self.tree.column(column, width=self._px(widths[column]), minwidth=self._px(60), anchor=anchor,
                             stretch=column in {"name", "path"})
            self.tree.heading(column, text="", anchor=anchor, command=lambda c=column: self._sort_by(c))
        self.tree.tag_configure("even", background=COLORS["table"])
        self.tree.tag_configure("odd", background=COLORS["table_alt"])
        self.tree.tag_configure("corrupted", foreground=COLORS["error"])
        self.tree.tag_configure("encrypted", foreground=COLORS["warning"])
        self.tree.tag_configure("unreadable", foreground=COLORS["unreadable"])
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
        # Shown over the table only while it is empty; see _update_count_label.
        self.empty_hint = ttk.Label(table_frame, style="Empty.TLabel", justify=tk.CENTER)

        footer = ttk.Frame(self.root, style="TFrame", padding=(self._px(16), self._px(3)))
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_credit = ttk.Label(footer, style="Credit.TLabel", cursor="hand2")
        self.lbl_credit.pack(side=tk.RIGHT)
        self.lbl_credit.bind("<Button-1>", lambda _e: webbrowser.open(AUTHOR_URL))

        # Status bar: message on the left; skipped folders, row count and progress on the right.
        bottom = ttk.Frame(self.root, style="Panel.TFrame", padding=(self._px(16), self._px(7)))
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        # Packed before the message so a long status text cannot squeeze these out.
        status_right = ttk.Frame(bottom, style="Panel.TFrame")
        status_right.pack(side=tk.RIGHT)
        # Packed only after a scan that skipped folders; see _finish_scan.
        self.btn_skipped = ttk.Button(status_right, style="Link.TButton", compound=tk.LEFT,
                                      image=self._photo("warning", self._px(16), COLORS["warning"], self._px(6)),
                                      command=self._show_skipped_folders)
        self.count_label = ttk.Label(status_right, style="Count.TLabel")
        self.count_label.pack(side=tk.LEFT)
        # Packed only while a scan runs; see _start_scan and _finish_scan.
        self.progress = ttk.Progressbar(status_right, orient=tk.HORIZONTAL, length=self._px(220), mode="determinate")
        self.lbl_status = ttk.Label(bottom, style="Muted.TLabel", anchor=tk.W)
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def shortcut(key: str, combo: str) -> Callable[[], str]:
            return lambda: f"{self._t(key)}  ({combo})"

        self._tooltips = [
            Tooltip(self.btn_browse, shortcut("choose_folder", "Ctrl+O")),
            Tooltip(self.lbl_resources, lambda: self._t("menu_resources")),
            Tooltip(self.resource_combo, lambda: self._t("menu_resources")),
            Tooltip(self.btn_scan, lambda: shortcut("cancel_scan" if self.is_scanning else "scan", "Ctrl+R")()),
            Tooltip(self.btn_settings, lambda: self._t("settings_hint")),
            Tooltip(self.btn_clear, lambda: f"{self._t('clear')}  (Esc)" if self.search_var.get() else ""),
            Tooltip(self.btn_clean, lambda: self._t("tool_clean")),
            Tooltip(self.btn_undo, lambda: self._t("tool_undo")),
            Tooltip(self.btn_export, shortcut("export", "Ctrl+E")),
        ]
        self._bind_shortcuts()
        self._sync_search_box()
        self._update_count_label()

    def _show_settings_menu(self) -> None:
        button = self.btn_settings
        self.settings_menu.update_idletasks()
        # Right-aligned under the gear, which sits at the window's right edge.
        x = button.winfo_rootx() + button.winfo_width() - self.settings_menu.winfo_reqwidth()
        try:
            self.settings_menu.tk_popup(max(0, x), button.winfo_rooty() + button.winfo_height())
        finally:
            self.settings_menu.grab_release()

    def _sync_search_box(self) -> None:
        """Show the placeholder while the search box is empty and the clear button while it is not."""
        if self.search_var.get():
            self.search_placeholder.place_forget()
            self.btn_clear.configure(image=self._clear_icons[0], cursor="hand2")
        else:
            self.search_placeholder.place(in_=self.search_entry, x=self._px(3), rely=0.5, anchor=tk.W)
            self.btn_clear.configure(image=self._clear_icons[1], cursor="")

    def _bind_shortcuts(self) -> None:
        def when_no_dialog(handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
            # bind_all also reaches widgets inside the modal rename dialog.
            return lambda event: None if self._rename_dialog is not None else handler(event)

        shortcuts: dict[str, Callable[[Any], Any]] = {
            "f": lambda _e: self._focus_search(),
            "o": lambda _e: self._select_folder(),
            "r": lambda _e: self._start_scan(),
            "e": lambda _e: self._export_csv(),
            "a": self._select_all_visible,
        }
        self._shortcut_handlers: dict[str, Callable[[Any], Any]] = {}
        for key, handler in shortcuts.items():
            # Caps Lock turns the keysym upper-case, so bind both spellings.
            for keysym in (key, key.upper()):
                self._shortcut_handlers[f"<Control-{keysym}>"] = when_no_dialog(handler)
        self._shortcut_handlers["<Escape>"] = when_no_dialog(lambda _e: self._clear_search())
        # Shift+C reports keysym "C"; with Caps Lock on it reports "c".
        for keysym in ("C", "c"):
            self._shortcut_handlers[f"<Control-Shift-{keysym}>"] = when_no_dialog(self._copy_selected_path)
        for sequence, handler in self._shortcut_handlers.items():
            self.root.bind_all(sequence, handler)

    # ---------- Language, settings and status ----------
    def _update_language(self) -> None:
        self.root.title(self._t("title"))
        self.lbl_target.config(text=self._t("target_dir"))
        self.btn_browse.config(text=self._t("browse"))
        self.btn_export.config(text=self._t("btn_export"))
        self.search_placeholder.config(text=self._t("search_hint"))
        self.duplicates_only.config(text=self._t("duplicates_only"))
        self.btn_skipped.config(text=self._t("skipped_button", count=len(self._skipped_folders)))
        self.menubar.entryconfigure(0, label=self._t("menu_file"))
        self.menubar.entryconfigure(1, label=self._t("menu_tools"))
        self.menubar.entryconfigure(2, label=self._t("menu_help"))
        self.help_menu.entryconfigure(0, label=self._t("menu_about"))
        self.help_menu.entryconfigure(1, label="keremaydin.net")
        self.btn_clean.config(text=self._t("btn_clean"))
        self.lbl_credit.config(text=self._t("credit"))
        self._resource_labels = {
            self._t("resource_choice", level=self._t("level_" + level),
                    workers=resource_profile(level, self.resource_governor.cpus).workers): level
            for level in RESOURCE_LEVELS
        }
        self.resource_combo.configure(values=list(self._resource_labels.keys()))
        self._sync_resource_combo()
        self.file_menu.entryconfigure(0, label=self._t("menu_select_folder"))
        self.file_menu.entryconfigure(2, label=self._t("export"))
        self.file_menu.entryconfigure(4, label=self._t("menu_exit"))
        self.tools_menu.entryconfigure(0, label=self._t("tool_clean"))
        self.tools_menu.entryconfigure(1, label=self._t("tool_undo"))
        self.tools_menu.entryconfigure(3, label=self._t("menu_resources"))
        self.resources_menu.entryconfigure(0, label=self._t("resources_detected", cpus=self.resource_governor.cpus))
        for index, level in enumerate(RESOURCE_LEVELS, start=2):
            workers = resource_profile(level, self.resource_governor.cpus).workers
            self.resources_menu.entryconfigure(index, label=self._t("resource_" + level, workers=workers))
        self.language_var.set(self.current_lang)
        self.separator_var.set(self.csv_separator)
        for menu, first, separator_menu in self._settings_menus:
            menu.entryconfigure(first, label=self._t("language"))
            menu.entryconfigure(first + 1, label=self._t("csv_separator"))
            for index, key in enumerate(CSV_SEPARATORS):
                separator_menu.entryconfigure(index, label=self._t("sep_" + key))
        for column in self.columns:
            heading = self._t("col_" + column)
            if self._sort_column == column:
                heading += "  " + ("▼" if self._sort_reverse else "▲")
            self.tree.heading(column, text=heading)
        self._update_action_states()
        self._render_last_status()
        self._update_count_label()

    def _update_action_states(self) -> None:
        """Enable or disable buttons and menu entries for the current scan state."""
        idle = not self.is_scanning
        has_rows = bool(self.records)
        cancelling = self.is_scanning and self._cancel_event.is_set()
        scan_label = self._t("cancel_scan" if self.is_scanning else "scan")
        # While scanning the primary button turns into a red Cancel scan with a stop icon.
        self.btn_scan.configure(text=scan_label, state=tk.DISABLED if cancelling else tk.NORMAL,
                                style="Danger.TButton" if self.is_scanning else "Accent.TButton",
                                image=self._icon("stop" if self.is_scanning else "play", COLORS["white"]))
        self.btn_browse.configure(state=tk.NORMAL if idle else tk.DISABLED)
        self.btn_export.configure(state=tk.NORMAL if idle and has_rows else tk.DISABLED)
        self.file_menu.entryconfigure(0, state=tk.NORMAL if idle else tk.DISABLED)
        self.file_menu.entryconfigure(1, label=scan_label, state=tk.DISABLED if cancelling else tk.NORMAL)
        self.file_menu.entryconfigure(2, state=tk.NORMAL if idle and has_rows else tk.DISABLED)
        self.tools_menu.entryconfigure(0, state=tk.NORMAL if idle and has_rows else tk.DISABLED)
        self.tools_menu.entryconfigure(1, state=tk.NORMAL if idle else tk.DISABLED)
        self.btn_clean.configure(state=tk.NORMAL if idle and has_rows else tk.DISABLED)
        self.btn_undo.configure(state=tk.NORMAL if idle else tk.DISABLED)

    def _on_language_change(self) -> None:
        self.current_lang = self.language_var.get() if self.language_var.get() in TRANSLATIONS else "en"
        self._save_settings()
        self._search_keys.clear()  # Page and duplicate labels are part of the search text.
        for path in self.records:
            self._mark_path_dirty(path)
        self._update_language()
        self._refresh_table(full=True)

    def _sync_resource_combo(self) -> None:
        level = self.resource_level_var.get()
        self.resource_combo.set(next(label for label, key in self._resource_labels.items() if key == level))

    def _on_resource_combo_change(self, _event: Any = None) -> None:
        self.resource_level_var.set(self._resource_labels.get(self.resource_combo.get(), DEFAULT_RESOURCE_LEVEL))
        self._on_resource_level_change()

    def _on_resource_level_change(self) -> None:
        previous = self.resource_governor.level
        self.resource_governor.set_level(self.resource_level_var.get())
        self._sync_resource_combo()
        level = self.resource_governor.level
        details = {"level": self._t("level_" + level), "workers": self.resource_governor.profile.workers}
        if not self.is_scanning:
            self._set_status("status_resources", **details)
            return
        if level == previous:
            return
        # Mid-scan the progress text keeps updating, so the notice rides along with it for a while.
        faster = RESOURCE_LEVELS.index(level) > RESOURCE_LEVELS.index(previous)
        self._resource_notice = ("resource_notice_up" if faster else "resource_notice_down", details)
        self._resource_notice_until = time.monotonic() + RESOURCE_NOTICE_SECONDS
        if self._resource_notice_job is not None:
            self.root.after_cancel(self._resource_notice_job)
        self._resource_notice_job = self.root.after(int(RESOURCE_NOTICE_SECONDS * 1000), self._expire_resource_notice)
        self._render_last_status()

    def _expire_resource_notice(self) -> None:
        self._resource_notice_job = None
        self._resource_notice = None
        self._render_last_status()

    def _on_separator_change(self) -> None:
        self.csv_separator = self.separator_var.get() if self.separator_var.get() in CSV_SEPARATORS else "auto"
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
        if (self.is_scanning and self._resource_notice is not None
                and time.monotonic() < self._resource_notice_until):
            notice_key, notice_kwargs = self._resource_notice
            text += "  ·  " + self._t(notice_key, **notice_kwargs)
        self.lbl_status.config(text=text)

    # ---------- Folder and scan controls ----------
    def _select_folder(self) -> None:
        if self.is_scanning:
            return
        selected = filedialog.askdirectory(initialdir=self.target_directory, title=self._t("choose_folder"))
        if selected:
            self.target_directory = os.path.normpath(selected)
            self.path_var.set(self.target_directory)
            self._set_status("status_ready")

    def _start_scan(self) -> None:
        if self.is_scanning:
            self._cancel_scan()
            return
        root_path = Path(self.target_directory).expanduser()
        if not root_path.exists() or not root_path.is_dir():
            messagebox.showerror(self._t("msg_error"), self._t("msg_invalid_folder"))
            return

        # Detached rows are not among get_children(), so forget every row this table created.
        self._forget_rows(list(self._iid_by_path))
        self.records = {}
        self._search_keys.clear()
        self._pending_render_paths.clear()
        self._pending_render_set.clear()
        self._visible_paths.clear()
        self.search_var.set("")
        self._table_mode = None
        self._sort_column = None
        self._sort_reverse = False
        self._cancel_event = threading.Event()
        self._skipped_dirs = 0
        self._skipped_folders = []
        self.btn_skipped.pack_forget()
        self.progress.stop()
        self.progress.configure(mode="indeterminate", maximum=100)
        self.progress.pack(side=tk.LEFT, padx=(self._px(12), 0))
        self.progress.start(12)
        self.is_scanning = True
        self._update_language()
        self._set_status("status_discovering", files=0, folders=0)
        self._scan_thread = threading.Thread(target=self._scan_worker, args=(root_path,), daemon=True,
                                             name="PDFInventoryScanner")
        self._scan_thread.start()

    def _cancel_scan(self) -> None:
        if self.is_scanning and not self._cancel_event.is_set():
            self._cancel_event.set()
            self._update_action_states()
            self._set_status("status_cancelling")

    def _scan_worker(self, root_path: Path) -> None:
        scan_folder(root_path, self._cancel_event, lambda kind, payload: self._queue.put((kind, payload)),
                    self.resource_governor)

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
                self._set_status("status_scanning", current=0, total=payload)
            elif kind in {"file", "file_update"}:
                self._store_record(payload)
                changed = True
            elif kind == "inspect_progress":
                current, total = payload
                self.progress.configure(value=current, maximum=max(1, total))
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
                groups = payload["groups"]
                for path, state in payload["states"].items():
                    record = self.records.get(path)
                    if record:
                        record["duplicate"] = state
                        record["duplicate_group"] = groups.get(path)
                        self._search_keys.pop(path, None)
                        self._mark_path_dirty(path)
                changed = True
            elif kind == "done":
                self._finish_scan(payload)
                changed = True
        if changed or self._refresh_pending:
            # While scanning, sorted or filtered views rebuild at most once per interval.
            self._refresh_table(throttle=self.is_scanning)
        self.root.after(100, self._poll_worker_queue)

    def _store_record(self, record: dict[str, Any]) -> None:
        path = record["path"]
        self.records[path] = record
        self._search_keys.pop(path, None)
        self._mark_path_dirty(path)

    def _finish_scan(self, summary: dict[str, Any]) -> None:
        self.is_scanning = False
        self._resource_notice = None  # Belongs to this scan's progress text only.
        self._has_scanned = True
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.progress.pack_forget()
        self._update_action_states()
        # "Checking…" becomes "Unknown" once the scan ends, which changes the cell and search text.
        for path, record in self.records.items():
            if record.get("duplicate") is None:
                self._search_keys.pop(path, None)
                self._mark_path_dirty(path)
        self._skipped_dirs = int(summary.get("skipped_dirs", self._skipped_dirs))
        self._skipped_folders = list(summary.get("skipped_folders", []))
        if self._skipped_folders:
            self.btn_skipped.config(text=self._t("skipped_button", count=len(self._skipped_folders)))
            self.btn_skipped.pack(side=tk.LEFT, padx=(0, self._px(14)), before=self.count_label)
        count = len(self.records)
        duplicates, groups, reclaimable = self._duplicate_summary()
        corrupt = sum(1 for rec in self.records.values() if rec.get("page_state") == "corrupt")
        errors = sum(1 for rec in self.records.values() if rec.get("page_state") == "unreadable")
        if summary.get("error"):
            self._set_status("status_scan_error", error=summary["error"])
        elif summary.get("cancelled"):
            self._set_status("status_cancelled", count=count, duplicates=duplicates)
        elif count == 0:
            self._set_status("status_no_pdf")
        else:
            self._set_status("status_done", count=count, duplicates=duplicates, groups=groups,
                             reclaimable=self._format_size(reclaimable), corrupt=corrupt,
                             errors=errors, skipped=self._skipped_dirs)
        self._save_settings()

    def _duplicate_summary(self) -> tuple[int, int, int]:
        """Return duplicate files, duplicate groups and bytes freed by keeping one copy per group."""
        members: dict[int, set[Any]] = defaultdict(set)
        sizes: dict[int, int] = {}
        duplicates = 0
        for record in self.records.values():
            group = record.get("duplicate_group")
            if record.get("duplicate") is True and group is not None:
                duplicates += 1
                # Hard links share storage, so they count once toward reclaimable space.
                members[group].add(record.get("file_id") or record["path"])
                sizes[group] = record.get("size_bytes") or 0
        reclaimable = sum(sizes[group] * (len(files) - 1) for group, files in members.items())
        return duplicates, len(members), reclaimable

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

    def _on_search_changed(self, *_args: Any) -> None:
        self._sync_search_box()
        if self._search_after_id:
            try:
                self.root.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
        self._search_after_id = self.root.after(160, self._apply_search)

    def _apply_search(self) -> None:
        self._search_after_id = None
        self._refresh_table(full=True)

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
        self._refresh_table(full=True)
        self._update_language()

    def _search_entry(self, record: dict[str, Any]) -> tuple[str, str, str, str]:
        path = record["path"]
        entry = self._search_keys.get(path)
        if entry is None:
            name = normalize_search(record.get("name", ""))
            folder = normalize_search(record.get("folder", ""))
            full_path = normalize_search(path)
            labels = normalize_search(" ".join((self._page_display(record), self._duplicate_display(record),
                                                self._problem_display(record))))
            entry = (" ".join((name, folder, full_path, labels)), name, folder, full_path)
            self._search_keys[path] = entry
        return entry

    def _sort_value(self, record: dict[str, Any], column: str) -> Any:
        if column == "size":
            return record.get("size_bytes") if record.get("size_bytes") is not None else -1
        if column == "pages":
            return record.get("pages") if record.get("pages") is not None else -1
        if column == "date":
            return record.get("mtime") if record.get("mtime") is not None else -1
        if column == "duplicate":
            state = record.get("duplicate")
            if state is None:
                return (-1, 0)
            # Sorting by group keeps the copies of each file next to each other.
            return (1, record.get("duplicate_group") or 0) if state else (0, 0)
        if column == "problem":
            return normalize_search(self._problem_display(record))
        _text, name, folder, full_path = self._search_entry(record)
        return {"folder": folder, "path": full_path}.get(column, name)

    def _filtered_records(self) -> list[dict[str, Any]]:
        query = normalize_search(self.search_var.get().strip())
        records: list[dict[str, Any]] = list(self.records.values())
        if self.duplicates_only_var.get():
            records = [rec for rec in records if rec.get("duplicate") is True]
        if query:
            records = [rec for rec in records if query in self._search_entry(rec)[0]]
        if self._sort_column:
            column = self._sort_column
            records.sort(key=lambda rec: (self._sort_value(rec, column), self._search_entry(rec)[3]),
                         reverse=self._sort_reverse)
        return records

    def _on_filter_changed(self) -> None:
        self._refresh_table(full=True)

    def _refresh_table(self, full: bool = False, throttle: bool = False) -> None:
        """Update changed rows, then show the visible rows in order.

        Each record gets one tree item, created once and rebuilt only when the record changes.
        Searching, sorting and filtering only re-order or detach existing items.
        """
        query = normalize_search(self.search_var.get().strip())
        mode = (query, self._sort_column, self._sort_reverse, self.duplicates_only_var.get())
        # Only the plain arrival-order view can append new rows in place.
        incremental = not full and mode == ("", None, False, False) and self._table_mode == mode
        reorder_now = not incremental and not (
            throttle and time.monotonic() - self._last_full_refresh < SCAN_TABLE_REFRESH_SECONDS)

        dirty = self._pending_render_paths
        self._pending_render_paths = []
        self._pending_render_set.clear()
        added: list[str] = []
        for path in dirty:
            record = self.records.get(path)
            if record is None:
                continue
            iid = self._iid_for_path(path)
            values = self._row_values(record)
            if self.tree.exists(iid):
                self.tree.item(iid, values=values, tags=self._row_tags(record, self._row_stripe.get(iid, "even")))
            else:
                self.tree.insert("", tk.END, iid=iid, values=values, tags=self._row_tags(record, "even"))
                self._row_stripe[iid] = "even"
                added.append(iid)

        if incremental:
            self._visible_paths.extend(self._path_by_iid[iid] for iid in added)
        elif reorder_now:
            visible = self._filtered_records()
            visible_iids = [self._iid_for_path(record["path"]) for record in visible]
            self.tree.set_children("", *visible_iids)
            self._visible_paths = [record["path"] for record in visible]
            self._last_full_refresh = time.monotonic()
            selection = self.tree.selection()
            if selection:
                shown = set(visible_iids)
                kept = [iid for iid in selection if iid in shown]
                if len(kept) != len(selection):
                    self.tree.selection_set(kept)
        else:
            # Throttled during a scan: keep new rows hidden until the next re-ordering pass.
            if added:
                self.tree.detach(*added)
            self._refresh_pending = True
            return
        self._refresh_pending = False
        self._restripe()
        self._table_mode = mode
        self._update_count_label()

    def _restripe(self) -> None:
        """Alternate row backgrounds by position, retagging only rows whose stripe changed."""
        for index, path in enumerate(self._visible_paths):
            iid = self._iid_by_path[path]
            stripe = "even" if index % 2 == 0 else "odd"
            if self._row_stripe.get(iid) != stripe:
                self._row_stripe[iid] = stripe
                self.tree.item(iid, tags=self._row_tags(self.records[path], stripe))

    def _forget_rows(self, paths: Iterable[str]) -> None:
        iids = [self._iid_by_path.pop(path) for path in paths if path in self._iid_by_path]
        for iid in iids:
            self._path_by_iid.pop(iid, None)
            self._row_stripe.pop(iid, None)
        if iids:
            self.tree.delete(*iids)

    def _iid_for_path(self, path: str) -> str:
        iid = self._iid_by_path.get(path)
        if iid:
            return iid
        iid = "pdf_" + hashlib.sha256(path.encode("utf-8", errors="surrogatepass")).hexdigest()
        self._iid_by_path[path] = iid
        self._path_by_iid[iid] = path
        return iid

    def _row_tags(self, record: dict[str, Any], stripe: str) -> tuple[str, ...]:
        tags = [stripe]
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
            group = record.get("duplicate_group")
            return self._t("dup_group", group=group) if group else self._t("yes")
        if state is False:
            return self._t("no")
        return self._t("pending") if self.is_scanning else self._t("unknown")

    def _problem_display(self, record: dict[str, Any]) -> str:
        error = record.get("error")
        return one_line(error) if error else ""

    def _row_values(self, record: dict[str, Any]) -> tuple[str, ...]:
        mtime = record.get("mtime")
        try:
            date_text = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime is not None else "—"
        except (OSError, OverflowError, ValueError):
            date_text = "—"
        return (
            str(record.get("name", "")), str(record.get("folder", "")),
            self._format_size(record.get("size_bytes")), self._page_display(record), date_text,
            self._duplicate_display(record), self._problem_display(record), str(record.get("path", "")),
        )

    def _update_count_label(self) -> None:
        if not hasattr(self, "count_label"):
            return
        # _visible_paths always mirrors the table, so counting it costs nothing on idle ticks.
        self.count_label.config(text=self._t("count_label", visible=len(self._visible_paths),
                                             total=len(self.records)))
        if self.records or self.is_scanning:
            self.empty_hint.place_forget()
        else:
            self.empty_hint.config(text=self._t("status_no_pdf" if self._has_scanned else "empty_hint"))
            self.empty_hint.place(in_=self.tree, relx=0.5, rely=0.5, anchor=tk.CENTER)

    # ---------- Context actions and keyboard shortcuts ----------
    def _show_context_menu(self, event: Any) -> str:
        row = self.tree.identify_row(event.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            menu = tk.Menu(self.root, tearoff=False, **self._popup_menu_colors())
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
            self._open_path(paths[0], "msg_file_error")
        return "break"

    def _open_selected_folder(self) -> None:
        paths = self._selected_paths()
        if paths:
            self._open_path(str(Path(paths[0]).parent), "msg_folder_error")

    def _open_path(self, path: str, error_key: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror(self._t("msg_error"), self._t(error_key, error=exc))

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
        # Mid-scan rows would still say "Checking…", so export waits for the scan to finish.
        if self.is_scanning:
            return
        visible_records = self._filtered_records()
        if not visible_records:
            messagebox.showwarning(self._t("msg_warning"), self._t("msg_no_data"))
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{self._t('filename_prefix')}_{timestamp}.csv"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[(self._t("csv_files"), "*.csv"), (self._t("all_files"), "*.*")],
            initialdir=self.last_export_dir, initialfile=default_name, title=self._t("choose_export"),
        )
        if not save_path:
            return

        # Exact bytes follow the display columns so spreadsheets can sort and sum sizes.
        headers = [self._t("col_" + key) for key in self.columns] + [self._t("col_size_bytes")]
        rows = (self._row_values(record) + (record["size_bytes"] if record.get("size_bytes") is not None else "",)
                for record in visible_records)
        delimiter = resolve_csv_delimiter(self.csv_separator, self.current_lang)
        destination = Path(save_path)
        try:
            write_csv_export(destination, headers, rows, delimiter)
            self.last_export_dir = str(destination.parent)
            self._save_settings()
            self._set_status("status_exported", count=len(visible_records), path=str(destination))
        except (OSError, csv.Error, UnicodeError) as exc:
            messagebox.showerror(self._t("msg_error"), self._t("msg_export_error", error=exc))

    # ---------- Filename cleaner ----------
    def _open_filename_cleaner(self) -> None:
        if self.is_scanning or not self.records or self._rename_dialog is not None:
            return
        visible = self._filtered_records()
        plans = preflight_renames(plan_renames(Path(record["path"]) for record in visible))
        if not plans:
            messagebox.showinfo(self._t("clean_title"), self._t("clean_none", total=len(visible)))
            return
        self._show_rename_preview(plans, "clean", self._t("clean_intro", total=len(visible)))

    def _open_cleanup_undo(self) -> None:
        if self.is_scanning or self._rename_dialog is not None:
            return
        initial = self.reports_dir if self.reports_dir.is_dir() else Path(self.target_directory)
        selected = filedialog.askopenfilename(
            initialdir=str(initial), title=self._t("choose_report"),
            filetypes=[(self._t("csv_files"), "*.csv"), (self._t("all_files"), "*.*")],
        )
        if not selected:
            return
        report = Path(selected)
        plans, warnings = load_undo_plans(report)
        if not plans:
            if warnings:
                messagebox.showerror(self._t("msg_error"), self._t("undo_invalid", details="\n".join(warnings[:5])))
            else:
                messagebox.showinfo(self._t("undo_title"), self._t("undo_nothing"))
            return
        intro = self._t("undo_intro", report=report.name)
        if warnings:
            intro += " " + self._t("undo_ignored", count=len(warnings))
        self._show_rename_preview(preflight_renames(plans), "undo", intro)

    def _show_rename_preview(self, plans: list[RenamePlan], action: str, intro: str) -> tk.Toplevel:
        """Show planned renames in a modal dialog; nothing changes until the apply button is pressed."""
        ready = sum(1 for plan in plans if plan.status == "ready")
        dialog = tk.Toplevel(self.root)
        dialog.title(self._t("clean_title" if action == "clean" else "undo_title"))
        dialog.configure(bg=COLORS["panel"])
        dialog.transient(self.root)
        dialog.minsize(self._px(640), self._px(360))
        width, height = self._px(960), self._px(540)
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 3)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        frame = ttk.Frame(dialog, style="Panel.TFrame", padding=self._px(14))
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=intro, wraplength=width - self._px(40), justify=tk.LEFT).pack(
            fill=tk.X, pady=(0, self._px(10)))

        bottom = ttk.Frame(frame, style="Panel.TFrame")
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=(self._px(10), 0))
        table = ttk.Frame(frame, style="Panel.TFrame")
        table.pack(fill=tk.BOTH, expand=True)
        columns = ("status", "current", "new", "folder")
        tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        widths = {"status": 130, "current": 320, "new": 280, "folder": 260}
        for column in columns:
            tree.heading(column, text=self._t("col_" + column))
            tree.column(column, width=self._px(widths[column]), minwidth=self._px(80), anchor=tk.W,
                        stretch=column != "status")
        tree.tag_configure("blocked", foreground=COLORS["warning"])
        for index, plan in enumerate(plans):
            stripe = "even" if index % 2 == 0 else "odd"
            tags = (stripe,) if plan.status == "ready" else (stripe, "blocked")
            tree.insert("", tk.END, values=(
                self._t("rename_status_" + plan.status), plan.source.name,
                plan.destination.name if plan.destination else "", self._folder_label(plan.source.parent),
            ), tags=tags)
        tree.tag_configure("even", background=COLORS["table"])
        tree.tag_configure("odd", background=COLORS["table_alt"])
        scrollbar = ttk.Scrollbar(table, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(bottom, style="Muted.TLabel",
                  text=self._t("rename_counts", ready=ready, blocked=len(plans) - ready)).pack(side=tk.LEFT)
        apply_key = "clean_apply" if action == "clean" else "undo_apply"
        apply_button = ttk.Button(bottom, style="Accent.TButton", text=self._t(apply_key, count=ready),
                                  state=tk.NORMAL if ready else tk.DISABLED,
                                  command=lambda: self._run_rename_plans(plans, action, dialog))
        apply_button.pack(side=tk.RIGHT)
        ttk.Button(bottom, style="Neutral.TButton", text=self._t("cancel"),
                   command=lambda: self._close_rename_dialog(dialog)).pack(side=tk.RIGHT, padx=(0, self._px(8)))

        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_rename_dialog(dialog))
        dialog.bind("<Escape>", lambda _e: (self._close_rename_dialog(dialog), "break")[1])
        self._rename_dialog = dialog
        self._grab_when_viewable(dialog)
        (apply_button if ready else tree).focus_set()
        return dialog

    def _grab_when_viewable(self, dialog: tk.Toplevel, attempts: int = 5) -> None:
        # A grab fails until the window manager has shown the dialog; retry briefly.
        try:
            dialog.grab_set()
        except tk.TclError:
            if attempts > 1:
                dialog.after(100, lambda: dialog.winfo_exists() and self._grab_when_viewable(dialog, attempts - 1))

    def _folder_label(self, folder: Path) -> str:
        """Show a folder relative to the scanned folder, where the meaningful part of its path is."""
        root = Path(self.target_directory)
        try:
            relative = folder.relative_to(root)
        except ValueError:
            return str(folder)
        return root.name if relative == Path(".") else str(relative)

    def _close_rename_dialog(self, dialog: tk.Toplevel) -> None:
        if self._rename_dialog is dialog:
            self._rename_dialog = None
        dialog.destroy()

    def _run_rename_plans(self, plans: list[RenamePlan], action: str, dialog: tk.Toplevel) -> None:
        prefix = "pdf_filename_cleaner" if action == "clean" else "pdf_filename_cleaner_undo"
        dialog.configure(cursor="watch")
        dialog.update_idletasks()
        try:
            report_path = default_report_path(self.reports_dir, prefix)
            outcomes, report_error = run_renames(plans, report_path)
        except OSError as exc:
            dialog.configure(cursor="")
            messagebox.showerror(self._t("msg_error"), self._t("msg_report_error", error=exc), parent=dialog)
            return
        self._close_rename_dialog(dialog)
        self._apply_renamed_paths(outcomes)

        renamed = sum(1 for plan in outcomes if plan.status == "renamed")
        self._set_status("status_renamed" if action == "clean" else "status_restored", count=renamed)
        if report_error is not None:
            messagebox.showerror(self._t("msg_error"), self._t(
                "msg_report_final_error", error=report_error, log=log_file_path()))
            return
        message = self._t("clean_done" if action == "clean" else "undo_done",
                          renamed=renamed, total=len(outcomes), report=report_path)
        if renamed < len(outcomes):
            message += "\n\n" + self._t("rename_problems", count=len(outcomes) - renamed)
        messagebox.showinfo(self._t("clean_title" if action == "clean" else "undo_title"), message)

    def _apply_renamed_paths(self, outcomes: Iterable[RenamePlan]) -> None:
        """Move renamed records to their new paths, keeping the table order."""
        moved = {str(plan.source): plan.destination for plan in outcomes
                 if plan.status == "renamed" and plan.destination is not None}
        if not moved:
            return
        self._forget_rows(moved)
        records: dict[str, dict[str, Any]] = {}
        for path, record in self.records.items():
            destination = moved.get(path)
            if destination is not None:
                self._search_keys.pop(path, None)
                path = str(destination)
                record = {**record, "path": path, "name": destination.name}
                self._mark_path_dirty(path)
            records[path] = record
        self.records = records
        self._refresh_table(full=True)

    # ---------- Lifecycle ----------
    def _show_about(self) -> None:
        messagebox.showinfo(self._t("about_title"), self._t("about_text"), parent=self.root)

    def _on_close(self) -> None:
        self._closing = True
        if self.is_scanning:
            self._cancel_event.set()
        self._save_settings()
        if self._resource_notice_job is not None:
            self.root.after_cancel(self._resource_notice_job)
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
    configure_logging()
    enable_windows_dpi_awareness()
    root = tk.Tk()
    PDFInventoryApp(root)
    root.mainloop()
    # A cancelled scan or a stuck PDF parse can leave worker threads running, which would keep
    # the process alive after the window closes. Settings and reports are already saved here.
    if any(thread.is_alive() and not thread.daemon
           for thread in threading.enumerate() if thread is not threading.main_thread()):
        logging.shutdown()
        os._exit(0)


if __name__ == "__main__":
    main()
