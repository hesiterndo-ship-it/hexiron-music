"""
Per-chat player state management.

Each Telegram group gets its own isolated PlayerState with its own:
  - current song (NowPlaying)
  - queue state
  - playback status
  - loop mode
  - shuffle state
  - volume
  - player message ID
"""

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("hexiron.player_state")


# ── Loop Mode ───────────────────────────────────────────────────────


class LoopMode(enum.Enum):
    OFF = "off"
    CURRENT = "current"
    QUEUE = "queue"


# ── Now Playing ─────────────────────────────────────────────────────


@dataclass
class NowPlaying:
    """Represents the currently playing track."""
    title: str = ""
    artist: str = ""
    duration: int = 0
    file_path: str = ""
    source: str = "unknown"
    source_url: str = ""
    requested_by: int = 0
    requested_by_name: str = ""
    started_at: float = 0.0

    @property
    def display_title(self) -> str:
        if self.artist:
            return f"{self.title} — {self.artist}"
        return self.title

    @property
    def elapsed(self) -> int:
        return int(time.time() - self.started_at) if self.started_at else 0

    @property
    def source_label(self) -> str:
        labels = {
            "youtube": "YouTube",
            "tiktok": "TikTok",
            "generic": "Direct URL",
            "telegram": "Upload",
        }
        return labels.get(self.source, self.source.title())


# ── Player State ────────────────────────────────────────────────────


MAX_HISTORY = 20


@dataclass
class PlayerState:
    """Per-chat player state.  Each group gets one of these."""
    chat_id: int = 0
    is_playing: bool = False
    is_paused: bool = False
    now_playing: Optional[NowPlaying] = None
    loop_mode: LoopMode = LoopMode.OFF
    shuffle_enabled: bool = False
    volume: int = 100
    player_message_id: int = 0
    history: list = field(default_factory=list)

    def reset(self):
        """Reset to idle state without changing chat_id."""
        self.is_playing = False
        self.is_paused = False
        self.now_playing = None
        self.player_message_id = 0
        self.history.clear()

    def push_history(self, np: Optional["NowPlaying"]):
        """Record a track that just finished/was skipped, for the ⏮ Previous button."""
        if np is None:
            return
        self.history.append(np)
        if len(self.history) > MAX_HISTORY:
            self.history.pop(0)

    def pop_history(self) -> Optional["NowPlaying"]:
        """Pop the most recently played track off the history stack."""
        if not self.history:
            return None
        return self.history.pop()


# ── State Registry ──────────────────────────────────────────────────

_states: Dict[int, PlayerState] = {}


def get_state(chat_id: int) -> PlayerState:
    """Get or create the player state for a chat."""
    if chat_id not in _states:
        _states[chat_id] = PlayerState(chat_id=chat_id)
    return _states[chat_id]


def remove_state(chat_id: int):
    """Remove player state for a chat."""
    _states.pop(chat_id, None)


def active_chat_ids() -> list:
    """Return a list of chat IDs that have active player states."""
    return [cid for cid, s in _states.items() if s.is_playing]