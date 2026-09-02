"""
Favorites service: add, remove, list, and display user favorites.
"""

import logging
from typing import List, Tuple, Optional

import database
from utils.helpers import escape_html, format_duration

logger = logging.getLogger("hexiron.favorites")

# Pagination settings
PER_PAGE = 10


def add_to_favorites(
    user_id: int,
    title: str,
    artist: str = "",
    duration: int = 0,
    file_path: str = "",
    source: str = "search",
) -> bool:
    """Add a song to a user's favorites. Returns False if already exists."""
    return database.add_favorite(
        user_id, title, artist, duration, file_path, source
    )


def remove_from_favorites(user_id: int, title: str, artist: str = "") -> bool:
    """Remove a song from a user's favorites."""
    return database.remove_favorite(user_id, title, artist)


def get_user_favorites(
    user_id: int, page: int = 0
) -> Tuple[List[dict], int, int]:
    """
    Get a page of favorites for a user.

    Returns:
        (favorites_list, page_number, total_pages)
    """
    total = database.favorite_count(user_id)
    total_pages = max(1, -(-total // PER_PAGE))  # ceiling division
    page = max(0, min(page, total_pages - 1))
    offset = page * PER_PAGE
    favorites = database.get_favorites(user_id, limit=PER_PAGE, offset=offset)
    return favorites, page, total_pages


def format_favorites(favorites: list, page: int, total_pages: int) -> str:
    """Format favorites list into a Telegram-friendly message."""
    if not favorites:
        return "❤️ <b>Your Favorites</b>\n\nNo favorites yet.\n\nUse ❤️ button on a playing song to save it."

    lines = [f"❤️ <b>YOUR FAVORITES</b>  (page {page + 1}/{total_pages})\n"]

    for i, fav in enumerate(favorites):
        title = escape_html(fav.get("title", "Unknown"))
        artist = escape_html(fav.get("artist", ""))
        duration = format_duration(fav.get("duration", 0))
        num = page * PER_PAGE + i + 1
        artist_part = f"\n   👤 {artist}" if artist else ""
        lines.append(f"{num}. 🎵 {title}{artist_part}\n   ⏱ {duration}")

    return "\n".join(lines)


def format_favorite_item(fav: dict, index: int) -> str:
    """Format a single favorite item."""
    title = escape_html(fav.get("title", "Unknown"))
    artist = escape_html(fav.get("artist", ""))
    duration = format_duration(fav.get("duration", 0))
    artist_part = f" — {artist}" if artist else ""
    return f"{index}. 🎵 {title}{artist_part} ⏱ {duration}"
