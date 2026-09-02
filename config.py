import os
import sys
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ── Telegram credentials ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_HASH = os.getenv("API_HASH", "")
STRING_SESSION = os.getenv("STRING_SESSION", "")

try:
    API_ID = int(os.getenv("API_ID", "0"))
except ValueError:
    API_ID = 0

try:
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))
except ValueError:
    OWNER_ID = 0

# Additional admin user IDs (comma-separated)
try:
    ADMIN_IDS: List[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ]
except Exception:
    ADMIN_IDS = []

# ── Proxy ─────────────────────────────────────────────────────────────
SOCKS5_PROXY_URL = os.getenv("SOCKS5_PROXY_URL", "").strip()

# ── Central licensing API ─────────────────────────────────────────────
CENTRAL_API_URL = os.getenv("CENTRAL_API_URL", "http://localhost:8080")
CENTRAL_API_KEY = os.getenv("CENTRAL_API_KEY", "")
PRODUCT_ID = os.getenv("PRODUCT_ID", "music")
CENTRAL_BOT_USERNAME = os.getenv("CENTRAL_BOT_USERNAME", "")

# ── Storage paths ─────────────────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", "/data")
STORAGE_DIR = os.getenv("STORAGE_DIR", os.path.join(DATA_DIR, "storage"))
TEMP_DIR = os.getenv("TEMP_DIR", os.path.join(DATA_DIR, "temp"))
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", os.path.join(DATA_DIR, "downloads"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
CACHE_DIR = os.getenv("CACHE_DIR", os.path.join(DATA_DIR, "cache"))
LOG_DIR = os.getenv("LOG_DIR", os.path.join(DATA_DIR, "logs"))

# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", os.path.join(DATA_DIR, "hexiron.db"))

# ── AI integration (optional) ────────────────────────────────────────
AI_PROVIDER = os.getenv("AI_PROVIDER", "")  # e.g. "openai", "gemini"
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")

# ── Player defaults ──────────────────────────────────────────────────
try:
    DEFAULT_VOLUME = int(os.getenv("DEFAULT_VOLUME", "100"))
except ValueError:
    DEFAULT_VOLUME = 100

try:
    MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "200"))
except ValueError:
    MAX_QUEUE_SIZE = 200

try:
    MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
except ValueError:
    MAX_UPLOAD_SIZE_MB = 50

# ── Cleanup ──────────────────────────────────────────────────────────
try:
    TEMP_FILE_MAX_AGE_HOURS = int(os.getenv("TEMP_FILE_MAX_AGE_HOURS", "6"))
except ValueError:
    TEMP_FILE_MAX_AGE_HOURS = 6

try:
    CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "30"))
except ValueError:
    CLEANUP_INTERVAL_MINUTES = 30

# ── Provider settings ──────────────────────────────────────────────
# yt-dlp YouTube/TikTok extraction timeout
YTDLP_TIMEOUT = float(os.getenv("YTDLP_TIMEOUT", "30"))
# Generic URL download max size (bytes)
GENERIC_MAX_SIZE_BYTES = int(os.getenv("GENERIC_MAX_SIZE_BYTES", str(200 * 1024 * 1024)))
# Generic URL download timeout (seconds)
GENERIC_DOWNLOAD_TIMEOUT = float(os.getenv("GENERIC_DOWNLOAD_TIMEOUT", "120"))
# Optional: path to yt-dlp cookies file for age-restricted content
YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE", "")

# ── Logging ──────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def validate_config():
    """Fail fast with a clear message instead of a confusing traceback."""
    missing = []

    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")

    if API_ID == 0:
        missing.append("API_ID")

    if not API_HASH:
        missing.append("API_HASH")

    if OWNER_ID == 0:
        missing.append("OWNER_ID")

    if not STRING_SESSION:
        missing.append(
            "STRING_SESSION "
            "(run `python3 generate_session.py` once to create it; "
            "a userbot session is required for voice chats)"
        )

    if missing:
        print(
            "[HexIron] Missing required environment variable(s): "
            + ", ".join(missing)
            + "\nSet them in your VPS environment "
              "(or in a .env file next to main.py) before starting the bot.",
            file=sys.stderr,
        )
        sys.exit(1)


def ensure_directories():
    """Create all required directories at startup."""
    for d in (
        DATA_DIR,
        STORAGE_DIR,
        TEMP_DIR,
        DOWNLOAD_DIR,
        UPLOAD_DIR,
        CACHE_DIR,
        LOG_DIR,
    ):
        os.makedirs(d, exist_ok=True)
