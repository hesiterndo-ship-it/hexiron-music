"""
Unified MusicItem model.

Every music provider produces a MusicItem. The queue and player
work exclusively with MusicItem objects, making them source-agnostic.
"""

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class MusicSource(enum.Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    GENERIC = "generic"
    TELEGRAM = "telegram"
    UNKNOWN = "unknown"


@dataclass
class MusicItem:
    """
    A single music track, regardless of source.

    Providers populate whatever fields they can; the player only
    needs `local_path`, `title`, and `artist` at minimum.
    """
    title: str = ""
    artist: str = ""
    duration: int = 0
    source: str = "unknown"
    source_url: str = ""
    local_path: str = ""
    thumbnail: str = ""
    requested_by: int = 0
    requested_by_name: str = ""
    file_size: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        if self.artist:
            return f"{self.title} — {self.artist}"
        return self.title

    @property
    def source_label(self) -> str:
        labels = {
            "youtube": "YouTube",
            "tiktok": "TikTok",
            "generic": "Direct URL",
            "telegram": "Upload",
        }
        return labels.get(self.source, self.source.title())
