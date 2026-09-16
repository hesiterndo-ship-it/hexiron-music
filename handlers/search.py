"""
Search handler: caches search results for inline selection.

Stores search results in memory keyed by (chat_id, user_id) so that
the control panel callback handler can retrieve the selected result
without re-searching.
"""

import logging
import time
from typing import Dict, Tuple

logger = logging.getLogger("hexiron.search")

# In-memory cache: (chat_id, user_id) -> (timestamp, results_list)
_search_cache: Dict[Tuple[int, int], Tuple[float, list]] = {}
_CACHE_TTL = 300  # 5 minutes


def store_search_results(chat_id: int, user_id: int, results: list) -> str:
    """
    Store search results for later selection.
    Returns a cache key string.
    """
    _search_cache[(chat_id, user_id)] = (time.time(), results)
    return f"{chat_id}:{user_id}"


def get_cached_results(chat_id: int, user_id: int) -> list:
    """
    Retrieve cached search results for a user in a chat.
    Returns empty list if expired or missing.
    """
    key = (chat_id, user_id)
    entry = _search_cache.get(key)
    if entry is None:
        return []
    timestamp, results = entry
    if time.time() - timestamp > _CACHE_TTL:
        _search_cache.pop(key, None)
        return []
    return results


def _cleanup_expired_cache():
    """Remove expired cache entries."""
    now = time.time()
    expired = [
        k for k, (t, _) in _search_cache.items()
        if now - t > _CACHE_TTL
    ]
    for k in expired:
        _search_cache.pop(k, None)


# ── Register handlers ──────────────────────────────────────────────


def register_search_handlers(bot, calls):
    """Register search-related handlers."""
    # No additional message handlers needed — search is handled via
    # /search in admin.py and result selection in control_panel.py.
    # This function exists so main.py can call it.
    pass
