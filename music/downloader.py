"""
Music downloader — compatibility shim.

This module exposes the same public API that the rest of the codebase
already uses (search_and_download, search_results, download_by_id)
but delegates to the new modular provider system under the hood.

RadioJavan has been removed.  All music now flows through:
  music.sources.youtube  (search + download)
  music.sources.tiktok   (URL download)
  music.sources.generic  (direct URL download)
"""

import asyncio
import logging
from typing import Dict, List, Optional

from music.sources.router import (
    detect_source,
    search_music,
    download_music,
    search_and_download_music,
    available_providers,
)
from music.sources.item import MusicItem

logger = logging.getLogger("hexiron.downloader")


def _ensure_providers():
    """Log available providers on first use."""
    try:
        providers = available_providers()
        logger.info("Available music providers: %s", ", ".join(providers) or "NONE")
    except Exception:
        pass


# Run once at import
_ensure_providers()


# ── Public API (backward-compatible) ─────────────────────────────────


def search_and_download(query: str) -> Optional[Dict]:
    """
    Search and download the first result.

    This is the function called by handlers/player.py via asyncio.to_thread.
    It must be synchronous and return a dict.

    Result shape:
    {
        "title": str,
        "artist": str,
        "duration": int,
        "file_path": str,
        "video_id": str
    }
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Search query is empty.")

    # Run the async router in a new event loop (called via asyncio.to_thread)
    item = asyncio.run(_async_search_and_download(query))

    if item is None:
        return None

    return {
        "title": item.display_title,
        "artist": item.artist,
        "duration": item.duration,
        "file_path": item.local_path,
        "video_id": item.metadata.get("video_id", ""),
    }


async def _async_search_and_download(query: str) -> Optional[MusicItem]:
    """Async wrapper for search_and_download_music."""
    return await search_and_download_music(query)


def search_results(query: str) -> List[Dict]:
    """
    Search for music and return a list of results without downloading.

    Each result contains: id, title, artist, duration.
    This is the function called by handlers/admin.py and handlers/search.py.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Search query is empty.")

    items = asyncio.run(_async_search(query))

    results = []
    for i, item in enumerate(items):
        results.append({
            "id": item.metadata.get("video_id") or item.source_url or str(i),
            "title": item.display_title,
            "short_title": item.title,
            "artist": item.artist,
            "duration": item.duration,
            "source": item.source,
            "source_url": item.source_url,
            "thumbnail": item.thumbnail,
        })

    return results


async def _async_search(query: str) -> List[MusicItem]:
    return await search_music(query, limit=5)


def download_by_id(song_id: str) -> Optional[Dict]:
    """
    Download a specific song by its ID or URL.

    Returns: {title, artist, duration, file_path} or None.
    This is the function called by handlers/search.py.
    """
    if not song_id:
        return None

    item = asyncio.run(_async_download_by_id(song_id))

    if item is None:
        return None

    return {
        "title": item.display_title,
        "artist": item.artist,
        "duration": item.duration,
        "file_path": item.local_path,
    }


async def _async_download_by_id(song_id: str) -> Optional[MusicItem]:
    """Download by ID (treated as a URL or video ID)."""
    # If it looks like a URL, use it directly
    if song_id.startswith("http://") or song_id.startswith("https://"):
        item = MusicItem(
            source_url=song_id,
            title=song_id,
        )
        return await download_music(item)

    # Otherwise treat as a YouTube video ID
    item = MusicItem(
        source="youtube",
        source_url=f"https://www.youtube.com/watch?v={song_id}",
        metadata={"video_id": song_id},
        title=song_id,
    )
    return await download_music(item)
