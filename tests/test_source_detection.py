"""
Tests for the music source detection and provider system.

Tests cover:
  - Source detection (YouTube, TikTok, generic, search, unknown)
  - MusicItem model
  - Provider availability
  - URL validation / SSRF protection
  - MusicSource enum
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from music.sources.router import detect_source, available_providers
from music.sources.item import MusicItem, MusicSource
from music.sources.base import MusicProvider
from music.sources.generic import _validate_url, _is_private_ip


# ═══════════════════════════════════════════════════════════════════
# Source Detection — YouTube
# ═══════════════════════════════════════════════════════════════════


class TestYouTubeDetection:
    """YouTube URL detection."""

    def test_standard_url(self):
        assert detect_source("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

    def test_short_url(self):
        assert detect_source("https://youtu.be/dQw4w9WgXcQ") == "youtube"

    def test_shorts_url(self):
        assert detect_source("https://www.youtube.com/shorts/abc12345678") == "youtube"

    def test_embed_url(self):
        assert detect_source("https://www.youtube.com/embed/dQw4w9WgXcQ") == "youtube"

    def test_mobile_url(self):
        assert detect_source("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

    def test_music_url(self):
        assert detect_source("https://music.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

    def test_no_scheme(self):
        assert detect_source("youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

    def test_v_url(self):
        assert detect_source("https://youtube.com/v/dQw4w9WgXcQ") == "youtube"


# ═══════════════════════════════════════════════════════════════════
# Source Detection — TikTok
# ═══════════════════════════════════════════════════════════════════


class TestTikTokDetection:
    """TikTok URL detection."""

    def test_standard_url(self):
        assert detect_source("https://www.tiktok.com/@user/video/123456") == "tiktok"

    def test_vm_url(self):
        assert detect_source("https://vm.tiktok.com/ZSdAbCdEf/") == "tiktok"

    def test_vt_url(self):
        assert detect_source("https://vt.tiktok.com/ZSdAbCdEf/") == "tiktok"

    def test_no_scheme(self):
        assert detect_source("tiktok.com/@user/video/123") == "tiktok"


# ═══════════════════════════════════════════════════════════════════
# Source Detection — Generic URLs
# ═══════════════════════════════════════════════════════════════════


class TestGenericDetection:
    """Direct URL detection."""

    def test_direct_mp3(self):
        assert detect_source("https://example.com/song.mp3") == "generic"

    def test_direct_m4a(self):
        assert detect_source("https://cdn.example.com/track.m4a") == "generic"

    def test_http_url(self):
        assert detect_source("http://example.com/audio.wav") == "generic"

    def test_non_audio_url(self):
        assert detect_source("https://example.com/file.txt") == "generic"


# ═══════════════════════════════════════════════════════════════════
# Source Detection — Search queries
# ═══════════════════════════════════════════════════════════════════


class TestSearchDetection:
    """Search query detection."""

    def test_song_name(self):
        assert detect_source("The Weeknd Blinding Lights") == "search"

    def test_short_query(self):
        assert detect_source("jazz") == "search"

    def test_empty(self):
        assert detect_source("") == "unknown"

    def test_none(self):
        assert detect_source(None) == "unknown"


# ═══════════════════════════════════════════════════════════════════
# MusicItem model
# ═══════════════════════════════════════════════════════════════════


class TestMusicItem:
    """MusicItem dataclass tests."""

    def test_default_values(self):
        item = MusicItem()
        assert item.title == ""
        assert item.artist == ""
        assert item.duration == 0
        assert item.source == "unknown"
        assert item.source_url == ""
        assert item.local_path == ""
        assert item.file_size == 0

    def test_display_title_with_artist(self):
        item = MusicItem(title="Blinding Lights", artist="The Weeknd")
        assert item.display_title == "Blinding Lights — The Weeknd"

    def test_display_title_without_artist(self):
        item = MusicItem(title="Blinding Lights")
        assert item.display_title == "Blinding Lights"

    def test_source_label_youtube(self):
        item = MusicItem(source="youtube")
        assert item.source_label == "YouTube"

    def test_source_label_tiktok(self):
        item = MusicItem(source="tiktok")
        assert item.source_label == "TikTok"

    def test_source_label_generic(self):
        item = MusicItem(source="generic")
        assert item.source_label == "Direct URL"

    def test_source_label_telegram(self):
        item = MusicItem(source="telegram")
        assert item.source_label == "Upload"


# ═══════════════════════════════════════════════════════════════════
# MusicSource enum
# ═══════════════════════════════════════════════════════════════════


class TestMusicSourceEnum:
    """MusicSource enum values."""

    def test_youtube(self):
        assert MusicSource.YOUTUBE.value == "youtube"

    def test_tiktok(self):
        assert MusicSource.TIKTOK.value == "tiktok"

    def test_generic(self):
        assert MusicSource.GENERIC.value == "generic"

    def test_telegram(self):
        assert MusicSource.TELEGRAM.value == "telegram"


# ═══════════════════════════════════════════════════════════════════
# Provider availability
# ═══════════════════════════════════════════════════════════════════


class TestProviderAvailability:
    """Provider availability checks."""

    def test_available_providers_returns_list(self):
        result = available_providers()
        assert isinstance(result, list)

    def test_generic_always_available(self):
        """Generic provider should always be available."""
        result = available_providers()
        assert "generic" in result


# ═══════════════════════════════════════════════════════════════════
# SSRF protection
# ═══════════════════════════════════════════════════════════════════


class TestSSRFProtection:
    """URL validation for SSRF protection."""

    def test_blocks_loopback(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_blocks_private_10(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_blocks_private_172(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_blocks_private_192(self):
        assert _is_private_ip("192.168.1.1") is True

    def test_blocks_link_local(self):
        assert _is_private_ip("169.254.1.1") is True

    def test_blocks_zero(self):
        assert _is_private_ip("0.0.0.0") is True

    def test_allows_public(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_blocks_invalid(self):
        assert _is_private_ip("not-an-ip") is True
