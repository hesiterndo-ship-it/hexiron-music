"""
TikTok music provider.

Uses yt-dlp for TikTok audio extraction.
Best-effort — TikTok frequently changes its platform, so extraction
may fail. The bot must never crash on TikTok extraction failure.
"""

import logging
import os
import re
import subprocess
from typing import List, Optional

from config import YTDLP_TIMEOUT, DOWNLOAD_DIR
from music.sources.base import MusicProvider
from music.sources.item import MusicItem

logger = logging.getLogger("hexiron.tiktok")

_TT_CACHE_DIR = os.path.join(DOWNLOAD_DIR, "tiktok")

# TikTok URL patterns
_TT_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|vm\.|vt\.)?"
    r"(?:tiktok\.com/|"
    r"vm\.tiktok\.com/|"
    r"vt\.tiktok\.com/)",
    re.IGNORECASE,
)

_YTDL_TT_ARGS = [
    "--no-playlist",
    "--no-warnings",
    "--no-check-certificates",
    "--socket-timeout", str(int(YTDLP_TIMEOUT)),
]


class TikTokProvider(MusicProvider):
    name = "tiktok"

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def search(self, query: str, limit: int = 5) -> List[MusicItem]:
        """TikTok does not support search via yt-dlp. Returns empty list."""
        return []

    def download(self, item: MusicItem) -> Optional[MusicItem]:
        """
        Download audio from a TikTok URL.
        Returns None with a clean error if extraction fails.
        """
        url = item.source_url
        if not url:
            logger.error("TikTok download: no URL provided")
            return None

        if not self._is_tiktok_url(url):
            logger.error("TikTok download: not a TikTok URL: %s", url)
            return None

        os.makedirs(_TT_CACHE_DIR, exist_ok=True)

        output_template = os.path.join(_TT_CACHE_DIR, "%(id)s.%(ext)s")

        args = list(_YTDL_TT_ARGS)
        args.extend([
            url,
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_template,
            "--print", "after_move:filepath",
            "--no-overwrites",
        ])

        try:
            result = subprocess.run(
                ["yt-dlp"] + args,
                capture_output=True,
                text=True,
                timeout=YTDLP_TIMEOUT * 3,
            )
        except subprocess.TimeoutExpired:
            logger.error("TikTok extraction timed out for: %s", url)
            return None
        except FileNotFoundError:
            logger.error("yt-dlp not found for TikTok extraction")
            return None

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()[:500]
            logger.warning(
                "TikTok extraction failed (expected in many environments): %s",
                stderr,
            )
            return None

        # Parse output filepath
        filepath = None
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and os.path.isfile(line):
                filepath = line
                break

        if not filepath:
            logger.error("TikTok download: output file not found")
            return None

        # Extract metadata
        title = item.title or "TikTok Audio"
        artist = item.artist or ""

        if not title or title == url:
            meta_args = list(_YTDL_TT_ARGS)
            meta_args.extend([url, "--dump-json", "--skip-download"])
            try:
                meta_result = subprocess.run(
                    ["yt-dlp"] + meta_args,
                    capture_output=True, text=True, timeout=YTDLP_TIMEOUT,
                )
                if meta_result.returncode == 0 and meta_result.stdout.strip():
                    import json
                    meta = json.loads(meta_result.stdout.strip().split("\n")[0])
                    title = meta.get("title", title)
                    artist = meta.get("uploader", "") or meta.get("creator", "") or artist
                    item.duration = int(meta.get("duration") or 0)
            except Exception:
                pass

        file_size = os.path.getsize(filepath)

        return MusicItem(
            title=title,
            artist=artist,
            duration=item.duration,
            source="tiktok",
            source_url=item.source_url,
            local_path=filepath,
            file_size=file_size,
            metadata=item.metadata,
        )

    @staticmethod
    def _is_tiktok_url(url: str) -> bool:
        return bool(_TT_URL_RE.search(url))
