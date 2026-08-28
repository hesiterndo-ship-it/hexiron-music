import asyncio
import logging
import os
from functools import partial
from urllib.parse import urlparse, unquote

from pyrogram import Client, filters, idle
from pyrogram.handlers import MessageHandler
from pytgcalls import PyTgCalls
from pytgcalls import filters as pytgfilters
from pytgcalls.types import StreamEnded

from config import (
    API_HASH,
    API_ID,
    BOT_TOKEN,
    STRING_SESSION,
    validate_config,
)
from database import init_db
from handlers.admin import on_added_to_group, panel, start
from handlers.player import (
    on_stream_end,
    pause,
    play,
    queue_list,
    resume,
    skip,
    stop,
)
from utils.ffmpeg_setup import ensure_ffmpeg


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("hexiron")


# =========================================================
# SOCKS5 PROXY
# =========================================================

def get_proxy():
    """
    Read SOCKS5 proxy from:

        SOCKS5_PROXY_URL

    Supported formats:

        socks5://HOST:PORT

        socks5://USERNAME:PASSWORD@HOST:PORT

        socks5h://HOST:PORT

        socks5h://USERNAME:PASSWORD@HOST:PORT

    Example:

        socks5://hexironproxy:password@185.221.237.197:1080
    """

    proxy_url = os.getenv("SOCKS5_PROXY_URL", "").strip()

    # -----------------------------------------------------
    # Proxy is REQUIRED
    # -----------------------------------------------------

    if not proxy_url:
        raise RuntimeError(
            "SOCKS5_PROXY_URL is not set. "
            "The bot will not start without a SOCKS5 proxy."
        )

    try:
        parsed = urlparse(proxy_url)

        # -------------------------------------------------
        # Check protocol
        # -------------------------------------------------

        scheme = parsed.scheme.lower()

        if scheme not in ("socks5", "socks5h"):
            raise ValueError(
                "SOCKS5_PROXY_URL must start with "
                "socks5:// or socks5h://"
            )

        # -------------------------------------------------
        # Check host
        # -------------------------------------------------

        if not parsed.hostname:
            raise ValueError(
                "SOCKS5_PROXY_URL is missing HOST."
            )

        # -------------------------------------------------
        # Check port
        # -------------------------------------------------

        if not parsed.port:
            raise ValueError(
                "SOCKS5_PROXY_URL is missing PORT."
            )

        # -------------------------------------------------
        # Build Pyrogram proxy configuration
        # -------------------------------------------------

        proxy = {
            "scheme": "socks5",
            "hostname": parsed.hostname,
            "port": parsed.port,
        }

        # -------------------------------------------------
        # Optional username
        # -------------------------------------------------

        if parsed.username:
            proxy["username"] = unquote(parsed.username)

        # -------------------------------------------------
        # Optional password
        # -------------------------------------------------

        if parsed.password:
            proxy["password"] = unquote(parsed.password)

        # -------------------------------------------------
        # Do NOT print password
        # -------------------------------------------------

        logger.info(
            "SOCKS5 proxy configured: %s:%s",
            parsed.hostname,
            parsed.port,
        )

        logger.info(
            "Telegram connections will use the SOCKS5 proxy."
        )

        return proxy

    except ValueError:
        raise

    except Exception as e:
        raise RuntimeError(
            f"Invalid SOCKS5_PROXY_URL: {e}"
        ) from e


# =========================================================
# MAIN RUNNER
# =========================================================

async def run():

    # -----------------------------------------------------
    # Validate configuration
    # -----------------------------------------------------

    validate_config()

    # -----------------------------------------------------
    # Initialize database
    # -----------------------------------------------------

    init_db()

    # -----------------------------------------------------
    # Make sure FFmpeg exists
    # -----------------------------------------------------

    ensure_ffmpeg()

    # -----------------------------------------------------
    # Load SOCKS5 proxy
    # -----------------------------------------------------

    proxy = get_proxy()

    logger.info(
        "SOCKS5 proxy is READY."
    )

    # =====================================================
    # BOT CLIENT
    # =====================================================

    bot = Client(
        "hexiron_bot",

        api_id=API_ID,
        api_hash=API_HASH,

        bot_token=BOT_TOKEN,

        # IMPORTANT:
        # All Telegram API traffic from the bot
        # goes through SOCKS5.
        proxy=proxy,
    )

    # =====================================================
    # USERBOT CLIENT
    # =====================================================

    userbot = Client(
        "hexiron_userbot",

        api_id=API_ID,
        api_hash=API_HASH,

        session_string=STRING_SESSION,

        # IMPORTANT:
        # Userbot also uses the same SOCKS5 proxy.
        proxy=proxy,
    )

    # =====================================================
    # PYTGCalls
    # =====================================================

    calls = PyTgCalls(userbot)

    # =====================================================
    # COMMAND HANDLERS
    # =====================================================

    # /start
    bot.add_handler(
        MessageHandler(
            start,
            filters.command("start") & filters.private,
        )
    )

    # /admin
    bot.add_handler(
        MessageHandler(
            panel,
            filters.command("admin"),
        )
    )

    # When bot is added to group
    bot.add_handler(
        MessageHandler(
            on_added_to_group,
            filters.new_chat_members,
        )
    )

    # /play
    bot.add_handler(
        MessageHandler(
            partial(play, calls=calls),
            filters.command("play"),
        )
    )

    # /pause
    bot.add_handler(
        MessageHandler(
            partial(pause, calls=calls),
            filters.command("pause"),
        )
    )

    # /resume
    bot.add_handler(
        MessageHandler(
            partial(resume, calls=calls),
            filters.command("resume"),
        )
    )

    # /skip
    bot.add_handler(
        MessageHandler(
            partial(skip, calls=calls),
            filters.command("skip"),
        )
    )

    # /stop
    bot.add_handler(
        MessageHandler(
            partial(stop, calls=calls),
            filters.command("stop"),
        )
    )

    # /queue
    bot.add_handler(
        MessageHandler(
            queue_list,
            filters.command("queue"),
        )
    )

    # =====================================================
    # AUTO PLAY NEXT TRACK
    # =====================================================

    @calls.on_update(pytgfilters.stream_end())
    async def _on_stream_end(_, update: StreamEnded):
        await on_stream_end(
            bot,
            calls,
            update.chat_id,
        )

    # =====================================================
    # START
    # =====================================================

    logger.info(
        "HexIron Music starting..."
    )

    try:

        # -------------------------------------------------
        # Start Telegram bot
        # -------------------------------------------------

        logger.info(
            "Starting Telegram bot through SOCKS5..."
        )

        await bot.start()

        logger.info(
            "Telegram bot connected successfully."
        )

        # -------------------------------------------------
        # Start PyTgCalls / Userbot
        # -------------------------------------------------

        logger.info(
            "Starting Telegram userbot through SOCKS5..."
        )

        await calls.start()

        logger.info(
            "Telegram userbot connected successfully."
        )

        # -------------------------------------------------
        # Everything is ready
        # -------------------------------------------------

        logger.info(
            "HexIron Music is up and running."
        )

        # Keep application alive
        await idle()

    finally:

        logger.info(
            "Stopping HexIron Music..."
        )

        # -------------------------------------------------
        # Stop bot safely
        # -------------------------------------------------

        try:
            await bot.stop()
        except Exception as e:
            logger.warning(
                "Error while stopping bot: %s",
                e,
            )


# =========================================================
# ENTRY POINT
# =========================================================

def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()