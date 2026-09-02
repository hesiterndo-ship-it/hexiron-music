"""
Source detection and routing.

Automatically detects the source of a query (YouTube URL, TikTok URL,
direct media URL, or search query) and routes to the appropriate provider.

The player should NEVER import providers directly — it always goes through
this router.
"""

import logging
import re
from typing import List, Optional

from music.sources.item import MusicItem
from music.sources.youtube import YouTubeProvider
from music.sources.tiktok import TikTokProvider
from music.sources.generic import GenericProvider

logger = logging.getLogger("hexiron.router")

# ── Provider instances (singletons) ────────────────────────────────

_youtube = YouTubeProvider()
_tiktok = TikTokProvider()
_generic = GenericProvider()

# ── URL pattern detection ──────────────────────────────────────────

_YT_URL_RE = re.compile(
    r"(?:https?://)?"
    r"(?:www\.|m\.|music\.)?"
    r"(?:"
    r"youtube\.com/(?:watch\?.*?v=|shorts/|embed/|v/)|"
    r"youtu\.be/"
    r")"
    r"[\w-]{11}",
    re.IGNORECASE,
)

_TT_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|vm\.|vt\.)?"
    r"(?:tiktok\.com/|vm\.tiktok\.com/|vt\.tiktok\.com/)",
    re.IGNORECASE,
)

_MEDIA_EXT_RE = re.compile(
    r"\.(mp3|m4a|wav|ogg|opus|flac|wma|aac|ape|alac)(?:\?|$)",
    re.IGNORECASE,
)


def detect_source(query: str) -> str:
    """
    Detect the source type from a query string.
    Returns: "youtube", "tiktok", "generic", "search", or "unknown"
    """
    query = (query or "").strip()
    if not query:
        return "unknown"

    if _YT_URL_RE.search(query):
        return "youtube"

    if _TT_URL_RE.search(query):
        return "tiktok"

    if query.startswith(("http://", "https://")):
        return "generic"

    # Looks like a search query
    return "search"


def available_providers() -> List[str]:
    """Return a list of provider names that are currently available."""
    providers = []
    if _youtube.is_available():
        providers.append("youtube")
    if _tiktok.is_available():
        providers.append("tiktok")
    providers.append("generic")  # always available
    return providers


# ── Public API ─────────────────────────────────────────────────────


async def search_music(query: str, limit: int = 5) -> List[MusicItem]:
    """
    Search for music. Routes to YouTube search.
    Returns metadata-only items (no download).
    """
    query = (query or "").strip()
    if not query:
        return []

    source = detect_source(query)

    if source == "youtube":
        # Direct YouTube URL — extract metadata
        item = MusicItem(source_url=query, source="youtube")
        # Try to get metadata without downloading
        # For URLs, we just return the URL as a search result
        return [item]

    if source == "tiktok":
        item = MusicItem(source_url=query, source="tiktok", title="TikTok Audio")
        return [item]

    if source == "generic":
        item = MusicItem(source_url=query, source="generic", title="Direct URL")
        return [item]

    # Default: YouTube search
    if _youtube.is_available():
        return _youtube.search(query, limit=limit)

    logger.warning("No search provider available")
    return []


async def download_music(item: MusicItem) -> Optional[MusicItem]:
    """
    Download a music item using the appropriate provider.
    Returns a MusicItem with local_path set, or None on failure.
    """
    source = item.source
    url = item.source_url

    # Auto-detect source if not set
    if source == "unknown" or source == "search":
        if url:
            source = detect_source(url)
        else:
            source = "search"

    if source == "youtube" and url:
        if _youtube.is_available():
            return _youtube.download(item)
        logger.error("YouTube provider not available")
        return None

    if source == "tiktok" and url:
        if _tiktok.is_available():
            return _tiktok.download(item)
        logger.error("TikTok provider not available")
        return None

    if source == "generic" and url:
        return _generic.download(item)

    if source == "search":
        # Should not be called with search source — use search_and_download_music
        logger.error("download_music called with search source — use search_and_download_music")
        return None

    logger.error("Cannot download: unknown source %r", source)
    return None


async def search_and_download_music(
    query: str,
    requested_by: int = 0,
    requested_by_name: str = "",
) -> Optional[MusicItem]:
    """
    Search for music and download the first result.
    This is the main entry point used by handlers/player.py.

    Flow:
      1. Detect source from query
      2. For search queries → search YouTube → download first result
      3. For URLs → download directly
    """
    source = detect_source(query)

    if source in ("youtube", "tiktok", "generic"):
        # Direct URL — download immediately
        item = MusicItem(
            source_url=query,
            source=source,
            title=query,
            requested_by=requested_by,
            requested_by_name=requested_by_name,
        )
        result = await download_music(item)
        if result:
            result.requested_by = requested_by
            result.requested_by_name = requested_by_name
        return result

    # Search query → YouTube search
    if _youtube.is_available():
        results = _youtube.search(query, limit=1)
        if not results:
            return None
        item = results[0]
        item.requested_by = requested_by
        item.requested_by_name = requested_by_name
        return await download_music(item)

    logger.error("No provider available for search query: %s", query)
    return None
