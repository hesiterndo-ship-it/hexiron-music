import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is optional; env vars can also be set directly on the VPS
    pass

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

# اتصال به ربات فروش مرکزی HEXIRON SALES - برای چک اینکه این گروه لایسنس
# موزیک فعال داره یا نه. CENTRAL_API_KEY باید دقیقاً همون API_KEY باشه که
# توی .env ربات مرکزی گذاشتی.
CENTRAL_API_URL = os.getenv("CENTRAL_API_URL", "http://localhost:8080")
CENTRAL_API_KEY = os.getenv("CENTRAL_API_KEY", "")
PRODUCT_ID = os.getenv("PRODUCT_ID", "music")
CENTRAL_BOT_USERNAME = os.getenv("CENTRAL_BOT_USERNAME", "")


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
            "STRING_SESSION (run `python3 generate_session.py` once to create it — "
            "bots cannot join voice chats themselves, a userbot session is required)"
        )
    if not CENTRAL_API_KEY:
        missing.append("CENTRAL_API_KEY (باید دقیقاً همون API_KEY توی .env ربات فروش مرکزی باشه)")

    if missing:
        print(
            "[HexIron] Missing required environment variable(s): "
            + ", ".join(missing)
            + "\nSet them in your VPS environment (or in a .env file next to main.py) before starting the bot.",
            file=sys.stderr,
        )
        sys.exit(1)
