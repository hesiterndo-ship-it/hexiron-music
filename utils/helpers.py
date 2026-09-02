"""
Utility helpers used across the project.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("hexiron.helpers")


def is_owner(user_id: int) -> bool:
    """Legacy wrapper — prefer services.permissions.is_owner."""
    from config import OWNER_ID
    return user_id == OWNER_ID


def format_duration(seconds) -> str:
    """Format seconds into a human-readable duration string."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "?:??"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def truncate(text: str, max_len: int = 100) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def sanitize_filename(name: str) -> str:
    """Remove or replace characters unsafe for file names."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"_+", "_", name).strip("_. ")
    return name[:200] if name else "untitled"


def parse_time_string(time_str: str) -> Optional[int]:
    """Parse a time string like '1:30', '01:30', '1h30m' into seconds."""
    time_str = time_str.strip().lower()

    # Format: 1:30 or 01:30:00
    if ":" in time_str:
        parts = time_str.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None

    # Format: 1h30m, 30s, 2h
    total = 0
    match = re.findall(r"(\d+)\s*(h|m|s)", time_str)
    if match:
        for val, unit in match:
            val = int(val)
            if unit == "h":
                total += val * 3600
            elif unit == "m":
                total += val * 60
            elif unit == "s":
                total += val
        return total if total > 0 else None

    # Plain number = seconds
    try:
        return int(time_str)
    except ValueError:
        return None
