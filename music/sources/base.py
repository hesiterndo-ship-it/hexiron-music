"""
Abstract base class for music providers.

All providers (YouTube, TikTok, Generic, etc.) inherit from
MusicProvider and implement search() and download().
"""

import abc
import logging
from typing import List, Optional

from music.sources.item import MusicItem

logger = logging.getLogger("hexiron.providers")


class MusicProvider(abc.ABC):
    """
    Abstract music provider.

    Subclasses must implement:
      - search(query, limit) -> list of MusicItem (metadata only, no download)
      - download(item) -> MusicItem with local_path set
    """

    name: str = "unknown"

    @abc.abstractmethod
    def search(self, query: str, limit: int = 5) -> List[MusicItem]:
        """
        Search for music. Returns metadata-only MusicItem objects
        (no local_path set). Only invoked by the router, not by the player.
        """
        ...

    @abc.abstractmethod
    def download(self, item: MusicItem) -> Optional[MusicItem]:
        """
        Download a track. The input MusicItem must have source_url or
        metadata set. Returns a MusicItem with local_path populated,
        or None on failure.
        """
        ...

    def is_available(self) -> bool:
        """Override to check if the provider can be used right now."""
        return True
