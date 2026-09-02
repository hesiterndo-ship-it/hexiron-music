"""
Music sources — modular provider system.

Public API re-exported here for convenience:
  MusicItem, MusicSource, MusicProvider,
  detect_source, search_music, download_music,
  search_and_download_music, available_providers,
"""
from music.sources.item import MusicItem, MusicSource
from music.sources.base import MusicProvider
from music.sources.router import (
    detect_source,
    search_music,
    download_music,
    search_and_download_music,
    available_providers,
)

__all__ = [
    "MusicItem",
    "MusicSource",
    "MusicProvider",
    "detect_source",
    "search_music",
    "download_music",
    "search_and_download_music",
    "available_providers",
]
