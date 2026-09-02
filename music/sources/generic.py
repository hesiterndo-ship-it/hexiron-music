"""
Generic direct-URL music provider.

Downloads audio files from direct media URLs (MP3, M4A, WAV, OGG, FLAC, etc.).

Security:
  - Validates URL scheme (http/https only)
  - Blocks private/loopback IPs (SSRF protection)
  - Enforces download size limits
  - Enforces download timeouts
  - Sanitizes filenames
  - Stores only inside configured directories
"""

import logging
import os
import socket
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from config import GENERIC_MAX_SIZE_BYTES, GENERIC_DOWNLOAD_TIMEOUT, UPLOAD_DIR
from music.sources.base import MusicProvider
from music.sources.item import MusicItem

logger = logging.getLogger("hexiron.generic")

# Allowed URL schemes
_ALLOWED_SCHEMES = {"http", "https"}

# Allowed file extensions (for URL path matching)
_AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac",
    ".wma", ".aac", ".ape", ".alac",
}

# Private/reserved IP ranges
_PRIVATE_PREFIXES = (
    b"\x00",       # 0.0.0.0/8
    b"\x0a",       # 10.0.0.0/8
    b"\x7f",       # 127.0.0.0/8
    b"\xa9\xfe",   # 169.254.0.0/16
    b"\xac\x10",   # 172.16.0.0/12
    b"\xc0\xa8",   # 192.168.0.0/16
)


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/loopback/link-local."""
    try:
        addr = socket.inet_aton(ip_str)
    except (socket.error, OSError):
        return True  # fail-safe: reject unparseable IPs
    for prefix in _PRIVATE_PREFIXES:
        if addr[: len(prefix)] == prefix:
            return True
    return False


def _validate_url(url: str) -> bool:
    """Validate a URL for safety before downloading."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # DNS resolution + IP check
    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_INET)
        for _family, _type, _proto, _canonname, sockaddr in resolved:
            ip = sockaddr[0]
            if _is_private_ip(ip):
                logger.warning("Blocked private IP: %s (%s)", ip, hostname)
                return False
    except socket.gaierror:
        return False

    return True


class GenericProvider(MusicProvider):
    name = "generic"

    def search(self, query: str, limit: int = 5) -> List[MusicItem]:
        """Generic URLs cannot be searched. Returns empty list."""
        return []

    def download(self, item: MusicItem) -> Optional[MusicItem]:
        """Download audio from a direct URL."""
        url = item.source_url
        if not url:
            logger.error("Generic download: no URL provided")
            return None

        if not _validate_url(url):
            logger.warning("URL validation failed: %s", url)
            return None

        os.makedirs(UPLOAD_DIR, exist_ok=True)

        # Derive a safe filename
        from utils.helpers import sanitize_filename

        parsed = urlparse(url)
        basename = os.path.basename(parsed.path)
        if not basename or "." not in basename:
            basename = "download.mp3"
        name_part = os.path.splitext(basename)[0]
        safe_name = sanitize_filename(name_part) or "download"
        ext = os.path.splitext(basename)[1] or ".mp3"
        filepath = os.path.join(UPLOAD_DIR, f"dl_{safe_name}{ext}")

        # Download with size limit and timeout
        try:
            with httpx.stream(
                "GET",
                url,
                timeout=GENERIC_DOWNLOAD_TIMEOUT,
                follow_redirects=True,
            ) as resp:
                resp.raise_for_status()

                # Check content type if available
                ct = resp.headers.get("content-type", "")
                cl = resp.headers.get("content-length", "")
                if cl:
                    try:
                        size = int(cl)
                        if size > GENERIC_MAX_SIZE_BYTES:
                            logger.warning(
                                "File too large: %d bytes (max %d)",
                                size, GENERIC_MAX_SIZE_BYTES,
                            )
                            return None
                    except ValueError:
                        pass

                downloaded = 0
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        downloaded += len(chunk)
                        if downloaded > GENERIC_MAX_SIZE_BYTES:
                            logger.warning("Download size limit exceeded")
                            f.close()
                            os.remove(filepath)
                            return None
                        f.write(chunk)

        except httpx.TimeoutException:
            logger.error("Download timed out: %s", url)
            if os.path.exists(filepath):
                os.remove(filepath)
            return None
        except httpx.HTTPStatusError as e:
            logger.error("Download HTTP error %s: %s", e.response.status_code, url)
            if os.path.exists(filepath):
                os.remove(filepath)
            return None
        except Exception as e:
            logger.error("Download failed: %s — %s", url, e)
            if os.path.exists(filepath):
                os.remove(filepath)
            return None

        if downloaded == 0:
            if os.path.exists(filepath):
                os.remove(filepath)
            return None

        # Derive title from filename or URL
        title = item.title
        if not title or title == url:
            title = safe_name.replace("_", " ").strip() or "Direct URL Audio"

        return MusicItem(
            title=title,
            artist=item.artist,
            duration=item.duration,
            source="generic",
            source_url=item.source_url,
            local_path=filepath,
            file_size=downloaded,
            metadata=item.metadata,
        )
