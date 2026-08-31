import asyncio
import logging
import os
from functools import partial
from urllib.parse import urlparse

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

from handlers.admin import (
    on_added_to_group,
    panel,
    start,
)

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
# TELEGRAM PROXY
# =========================================================

def get_telegram_proxy():
    """
    Read SOCKS5 proxy configuration from environment.

    Expected format:

        socks5://HOST:PORT

    or:

        socks5://USERNAME:PASSWORD@HOST:PORT

    Also accepts:

        socks5h://HOST:PORT
        socks://HOST:PORT
    """

    proxy_url = os.getenv("SOCKS5_PROXY_URL", "").strip()

    if not proxy_url:
        logger.warning(
            "Telegram SOCKS5 proxy is NOT configured. "
            "Bot and Userbot will use direct connection."
        )
        return None

    try:
        parsed = urlparse(proxy_url)
    except Exception:
        logger.exception("Failed to parse SOCKS5_PROXY_URL")
        raise

    scheme = parsed.scheme.lower()

    if scheme not in ("socks5", "socks5h", "socks"):
        raise ValueError(
            "Unsupported proxy scheme. "
            f"Expected socks5/socks5h/socks, got: {parsed.scheme!r}"
        )

    if not parsed.hostname:
        raise ValueError(
            "SOCKS5_PROXY_URL must contain a hostname."
        )

    if not parsed.port:
        raise ValueError(
            "SOCKS5_PROXY_URL must contain a port."
        )

    proxy = {
        "scheme": "socks5",
        "hostname": parsed.hostname,
        "port": parsed.port,
    }

    if parsed.username:
        proxy["username"] = parsed.username

    if parsed.password:
        proxy["password"] = parsed.password

    # Never log username/password.
    logger.info(
        "Telegram SOCKS5 proxy enabled: %s:%s",
        parsed.hostname,
        parsed.port,
    )

    if parsed.username:
        logger.info(
            "Telegram SOCKS5 proxy authentication: enabled"
        )
    else:
        logger.info(
            "Telegram SOCKS5 proxy authentication: disabled"
        )

    return proxy


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
    # Ensure FFmpeg / FFprobe
    # -----------------------------------------------------

    ensure_ffmpeg()

    # -----------------------------------------------------
    # Telegram proxy
    # -----------------------------------------------------

    telegram_proxy = get_telegram_proxy()

    # -----------------------------------------------------
    # Persistent data directory
    # -----------------------------------------------------

    data_dir = os.getenv("DATA_DIR", "/data")

    logger.info(
        "Using Telegram data directory: %s",
        data_dir,
    )

    # =====================================================
    # BOT
    # =====================================================

    bot = Client(
        "hexiron_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        proxy=telegram_proxy,
        workdir=data_dir,
    )

    logger.info(
        "HexIron Bot configured."
    )

    # =====================================================
    # USERBOT / PYTGCalls
    # =====================================================

    userbot = Client(
        "hexiron_userbot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=STRING_SESSION,
        proxy=telegram_proxy,
        workdir=data_dir,
    )

    if telegram_proxy:
        logger.info(
            "HexIron Userbot is configured WITH SOCKS5 proxy "
            "for PyTgCalls."
        )
    else:
        logger.warning(
            "HexIron Userbot is configured WITHOUT SOCKS5 proxy. "
            "PyTgCalls will attempt a direct Telegram connection."
        )

    # =====================================================
    # PYTGCalls
    # =====================================================

    calls = PyTgCalls(userbot)

    logger.info(
        "PyTgCalls initialized using HexIron Userbot."
    )

    # =====================================================
    # NTGCALLS CONNECTION DEBUG
    # =====================================================

    def _on_ntgcalls_connection_change(chat_id, network_info):
        try:
            logger.info(
                "NTgCalls connection change: chat=%s kind=%s state=%s",
                chat_id,
                network_info.kind,
                network_info.state,
            )
        except Exception:
            logger.exception(
                "Failed to log NTgCalls connection state."
            )

    try:
        calls._binding.on_connection_change(
            _on_ntgcalls_connection_change
        )
        logger.info(
            "NTgCalls connection-state debug callback enabled."
        )
    except Exception:
        logger.exception(
            "Could not enable NTgCalls connection-state debug callback."
        )

    # =====================================================
    # BOT HANDLERS
    # =====================================================

    bot.add_handler(
        MessageHandler(
            start,
            filters.command("start") & filters.private,
        )
    )

    bot.add_handler(
        MessageHandler(
            panel,
            filters.command("admin"),
        )
    )

    bot.add_handler(
        MessageHandler(
            on_added_to_group,
            filters.new_chat_members,
        )
    )

    bot.add_handler(
        MessageHandler(
            partial(play, calls=calls),
            filters.command("play"),
        )
    )

    bot.add_handler(
        MessageHandler(
            partial(pause, calls=calls),
            filters.command("pause"),
        )
    )

    bot.add_handler(
        MessageHandler(
            partial(resume, calls=calls),
            filters.command("resume"),
        )
    )

    bot.add_handler(
        MessageHandler(
            partial(skip, calls=calls),
            filters.command("skip"),
        )
    )

    bot.add_handler(
        MessageHandler(
            partial(stop, calls=calls),
            filters.command("stop"),
        )
    )

    bot.add_handler(
        MessageHandler(
            queue_list,
            filters.command("queue"),
        )
    )

    # =====================================================
    # STREAM END HANDLER
    # =====================================================

    @calls.on_update(pytgfilters.stream_end())
    async def _on_stream_end(_, update: StreamEnded):
        await on_stream_end(
            bot,
            calls,
            update.chat_id,
        )

    # =====================================================
    # START SERVICES
    # =====================================================

    logger.info("HexIron Music starting...")

    try:

        # -------------------------------------------------
        # Start Bot
        # -------------------------------------------------

        logger.info(
            "Starting Telegram Bot..."
        )

        await bot.start()

        logger.info(
            "Telegram Bot started successfully."
        )

        # -------------------------------------------------
        # Start PyTgCalls / Userbot
        # -------------------------------------------------

        logger.info(
            "Starting PyTgCalls / Userbot..."
        )

        await calls.start()

        logger.info(
            "PyTgCalls / Userbot started successfully."
        )

        # -------------------------------------------------
        # Application ready
        # -------------------------------------------------

        logger.info(
            "HexIron Music is UP and RUNNING."
        )

        await idle()

    finally:

        # =================================================
        # STOP PYTGCalls
        # =================================================

        logger.info(
            "Stopping PyTgCalls..."
        )

        try:
            await calls.stop()

            logger.info(
                "PyTgCalls stopped successfully."
            )

        except Exception:
            logger.exception(
                "Failed to stop PyTgCalls cleanly."
            )

        # =================================================
        # STOP BOT
        # =================================================

        logger.info(
            "Stopping Telegram Bot..."
        )

        try:
            await bot.stop()

            logger.info(
                "Telegram Bot stopped successfully."
            )

        except Exception:
            logger.exception(
                "Failed to stop Telegram Bot cleanly."
            )


# =========================================================
# ENTRY POINT
# =========================================================

def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
