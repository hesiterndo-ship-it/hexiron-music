"""
Storage management: directory creation, temp file cleanup,
stale download cleanup, and disk usage reporting.
"""

import logging
import os
import shutil
import time

from config import (
    TEMP_DIR,
    DOWNLOAD_DIR,
    UPLOAD_DIR,
    CACHE_DIR,
    TEMP_FILE_MAX_AGE_HOURS,
)

logger = logging.getLogger("hexiron.storage")


def ensure_dirs():
    """Create all required storage directories."""
    for d in (TEMP_DIR, DOWNLOAD_DIR, UPLOAD_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)


def cleanup_temp_files() -> int:
    """
    Remove temporary files older than TEMP_FILE_MAX_AGE_HOURS.
    Returns the number of files removed.
    """
    removed = 0
    max_age = TEMP_FILE_MAX_AGE_HOURS * 3600
    now = time.time()

    for dir_path in (TEMP_DIR, CACHE_DIR):
        if not os.path.isdir(dir_path):
            continue
        for entry in os.scandir(dir_path):
            try:
                if entry.is_file():
                    age = now - entry.stat().st_mtime
                    if age > max_age:
                        os.remove(entry.path)
                        removed += 1
                elif entry.is_dir():
                    # Remove empty sub-directories older than threshold
                    age = now - entry.stat().st_mtime
                    if age > max_age:
                        try:
                            os.rmdir(entry.path)
                            removed += 1
                        except OSError:
                            pass
            except Exception:
                logger.debug("Failed to clean %s", entry.path)

    if removed:
        logger.info("Cleaned %d temp/cache files", removed)

    return removed


def cleanup_stale_downloads() -> int:
    """
    Remove downloaded files that are very old (3x TEMP_FILE_MAX_AGE_HOURS).
    Returns the number of files removed.
    """
    removed = 0
    max_age = TEMP_FILE_MAX_AGE_HOURS * 3 * 3600
    now = time.time()

    if not os.path.isdir(DOWNLOAD_DIR):
        return 0

    for entry in os.scandir(DOWNLOAD_DIR):
        try:
            if entry.is_file():
                age = now - entry.stat().st_mtime
                if age > max_age:
                    os.remove(entry.path)
                    removed += 1
        except Exception:
            logger.debug("Failed to clean %s", entry.path)

    if removed:
        logger.info("Cleaned %d stale download files", removed)

    return removed


def _dir_size_human(path: str) -> str:
    """Return a human-readable size for a directory."""
    if not os.path.isdir(path):
        return "N/A"
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except Exception:
        return "N/A"

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} PB"


def _disk_human(path: str) -> str:
    """Return human-readable free disk space."""
    try:
        usage = shutil.disk_usage(path)
        free = usage.free
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if free < 1024:
                return f"{free:.1f} {unit}"
            free /= 1024
        return f"{free:.1f} PB"
    except Exception:
        return "N/A"


def get_disk_usage() -> dict:
    """Return a dict with human-readable sizes for all storage dirs."""
    return {
        "downloads": _dir_size_human(DOWNLOAD_DIR),
        "uploads": _dir_size_human(UPLOAD_DIR),
        "temp": _dir_size_human(TEMP_DIR),
        "cache": _dir_size_human(CACHE_DIR),
        "disk_total": _disk_human(DOWNLOAD_DIR),
        "disk_free": _disk_human(DOWNLOAD_DIR),
    }
