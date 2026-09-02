"""
YouTube music provider.

Uses yt-dlp for:
  - YouTube search (flat extraction — no downloads)
  - YouTube URL audio extraction
  - YouTube Shorts support
  - Audio-only download with FFmpeg conversion

Configuration:
  YTDLP_TIMEOUT      — extraction timeout in seconds
  YTDLP_COOKIES_FILE — optional path to yt-dlp cookies file
  DOWNLOAD_DIR       — where to store downloaded audio
"""

import logging
import os
import re
import subprocess
from typing import List, Optional

from config import YTDLP_TIMEOUT, YTDLP_COOKIES_FILE, DOWNLOAD_DIR
from music.sources.base import MusicProvider
from music.sources.item import MusicItem

logger = logging.getLogger("hexiron.youtube")

# Cache directory for YouTube downloads
_YT_CACHE_DIR = os.path.join(DOWNLOAD_DIR, "youtube")

# YouTube URL patterns
_YT_URL_RE = re.compile(
    r"(?:https?://)?"
    r"(?:www\.|m\.|music\.)?"
    r"(?:"
    r"youtube\.com/(?:watch\?.*?v=|shorts/|embed/|v/)|"
    r"youtu\.be/"
    r")"
    r"([\w-]{11})",
    re.IGNORECASE,
)

# yt-dlp base arguments
_YTDL_BASE_ARGS = [
    "--no-playlist",
    "--no-warnings",
    "--no-check-certificates",
    "--geo-bypass",
    "--socket-timeout", str(int(YTDLP_TIMEOUT)),
]


class YouTubeProvider(MusicProvider):
    name = "youtube"

    def is_available(self) -> bool:
        """Check if yt-dlp is installed."""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ── Search ──────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 5) -> List[MusicItem]:
        """
        Search YouTube for music.
        Uses flat extraction (no downloads) to return metadata quickly.
        """
        args = list(_YTDL_BASE_ARGS)
        args.extend([
            f"ytsearch{limit}:{query}",
            "--flat-playlist",
            "--dump-json",
        ])

        if YTDLP_COOKIES_FILE and os.path.isfile(YTDLP_COOKIES_FILE):
            args.extend(["--cookies", YTDLP_COOKIES_FILE])

        try:
            result = subprocess.run(
                ["yt-dlp"] + args,
                capture_output=True,
                text=True,
                timeout=YTDLP_TIMEOUT + 10,
            )
        except subprocess.TimeoutExpired:
            logger.warning("YouTube search timed out for: %s", query)
            return []
        except FileNotFoundError:
            logger.error("yt-dlp not found. Install with: pip install yt-dlp")
            return []

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            # Don't log the full stderr for common "no results" cases
            if "No results" not in stderr and stderr:
                logger.warning("yt-dlp search stderr: %s", stderr[:500])
            return []

        items = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                import json
                data = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            video_id = data.get("id", "")
            title = data.get("title", "")
            uploader = data.get("uploader", "") or data.get("channel", "")
            duration = int(data.get("duration") or 0)

            if not video_id or not title:
                continue

            url = data.get("url") or data.get("webpage_url") or ""
            if not url:
                url = f"https://www.youtube.com/watch?v={video_id}"

            items.append(MusicItem(
                title=title,
                artist=uploader,
                duration=duration,
                source="youtube",
                source_url=url,
                metadata={"video_id": video_id},
            ))

        logger.info("YouTube search returned %d results for: %s", len(items), query)
        return items

    # ── Download ────────────────────────────────────────────────────

    def download(self, item: MusicItem) -> Optional[MusicItem]:
        """Download audio from a YouTube URL or video ID."""
        url = item.source_url
        if not url:
            video_id = item.metadata.get("video_id", "")
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                logger.error("YouTube download: no URL or video_id")
                return None

        os.makedirs(_YT_CACHE_DIR, exist_ok=True)

        output_template = os.path.join(_YT_CACHE_DIR, "%(id)s.%(ext)s")

        args = list(_YTDL_BASE_ARGS)
        args.extend([
            url,
            "-x",  # extract audio
            "--audio-format", "mp3",
            "--audio-quality", "0",  # best quality
            "-o", output_template,
            "--print", "after_move:filepath",
            "--no-overwrites",
        ])

        if YTDLP_COOKIES_FILE and os.path.isfile(YTDLP_COOKIES_FILE):
            args.extend(["--cookies", YTDLP_COOKIES_FILE])

        try:
            result = subprocess.run(
                ["yt-dlp"] + args,
                capture_output=True,
                text=True,
                timeout=YTDLP_TIMEOUT * 3,  # more time for download
            )
        except subprocess.TimeoutExpired:
            logger.error("YouTube download timed out for: %s", url)
            return None
        except FileNotFoundError:
            logger.error("yt-dlp not found")
            return None

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()[:500]
            logger.error("YouTube download failed: %s", stderr)
            return None

        # Parse the output filepath
        filepath = None
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and os.path.isfile(line):
                filepath = line
                break

        if not filepath:
            # Fallback: try to find the file by video_id
            video_id = item.metadata.get("video_id", "")
            if video_id:
                for ext in ("mp3", "opus", "m4a", "webm", "ogg"):
                    candidate = os.path.join(_YT_CACHE_DIR, f"{video_id}.{ext}")
                    if os.path.isfile(candidate):
                        filepath = candidate
                        break

        if not filepath:
            logger.error("YouTube download: output file not found")
            return None

        # Try to get metadata from yt-dlp
        if not item.title or item.title == item.source_url:
            meta_args = list(_YTDL_BASE_ARGS)
            meta_args.extend([
                url, "--dump-json", "--skip-download",
            ])
            if YTDLP_COOKIES_FILE and os.path.isfile(YTDLP_COOKIES_FILE):
                meta_args.extend(["--cookies", YTDLP_COOKIES_FILE])
            try:
                meta_result = subprocess.run(
                    ["yt-dlp"] + meta_args,
                    capture_output=True, text=True, timeout=YTDLP_TIMEOUT,
                )
                if meta_result.returncode == 0 and meta_result.stdout.strip():
                    import json
                    meta = json.loads(meta_result.stdout.strip().split("\n")[0])
                    item.title = meta.get("title", item.title)
                    item.artist = meta.get("uploader", "") or meta.get("channel", "") or item.artist
                    item.duration = int(meta.get("duration") or item.duration)
            except Exception:
                pass

        file_size = os.path.getsize(filepath)

        return MusicItem(
            title=item.title,
            artist=item.artist,
            duration=item.duration,
            source="youtube",
            source_url=item.source_url,
            local_path=filepath,
            file_size=file_size,
            metadata=item.metadata,
        )
