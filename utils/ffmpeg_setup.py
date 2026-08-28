"""Ensures ffmpeg/ffprobe are available on PATH.

py-tgcalls (via ntgcalls) shells out to `ffprobe` to inspect media files
even though audio decoding itself is handled by its bundled libav. On
Linux hosts without a package manager (no apt/dnf) and where the
filesystem resets periodically (e.g. free-tier containers), a one-time
manual install doesn't survive restarts, so this module downloads a
static ffmpeg/ffprobe build once per boot and prepends it to PATH. On
Windows/macOS (e.g. running the bot locally) it only checks whether
ffmpeg is already installed and prints instructions if not, since the
Linux static build isn't usable there.
"""
import logging
import os
import platform
import shutil
import tarfile
import urllib.request

logger = logging.getLogger("hexiron.ffmpeg_setup")

BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
FFMPEG_URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
ARCHIVE_PATH = "/tmp/ffmpeg-static.tar.xz"


def ensure_ffmpeg():
    """Make sure ffmpeg and ffprobe are importable from PATH."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    if platform.system() != "Linux":
        logger.warning(
            "ffmpeg/ffprobe not found on PATH. Install it manually for your OS, "
            "then restart the bot:\n"
            "  - Windows: winget install ffmpeg  (or download from https://ffmpeg.org/download.html)\n"
            "  - macOS:   brew install ffmpeg\n"
            "  - Linux:   use your package manager (apt/dnf/pacman install ffmpeg)"
        )
        return

    os.makedirs(BIN_DIR, exist_ok=True)

    # Already extracted from a previous boot in this same filesystem?
    if os.path.exists(os.path.join(BIN_DIR, "ffmpeg")) and os.path.exists(
        os.path.join(BIN_DIR, "ffprobe")
    ):
        _add_to_path()
        return

    logger.info("ffmpeg/ffprobe not found — downloading a static build...")
    try:
        urllib.request.urlretrieve(FFMPEG_URL, ARCHIVE_PATH)
        with tarfile.open(ARCHIVE_PATH, mode="r:xz") as tar:
            members = [
                m for m in tar.getmembers()
                if m.name.endswith("/ffmpeg") or m.name.endswith("/ffprobe")
            ]
            tar.extractall("/tmp", members=members)
            for m in members:
                src = os.path.join("/tmp", m.name)
                dst = os.path.join(BIN_DIR, os.path.basename(m.name))
                shutil.move(src, dst)
                os.chmod(dst, 0o755)
        _add_to_path()
        logger.info("ffmpeg/ffprobe installed to %s", BIN_DIR)
    except Exception as e:
        logger.error("Failed to auto-install ffmpeg: %s", e)
    finally:
        if os.path.exists(ARCHIVE_PATH):
            os.remove(ARCHIVE_PATH)


def _add_to_path():
    if BIN_DIR not in os.environ.get("PATH", ""):
        os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")
