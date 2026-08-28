```python
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
    Read SOCKS5 proxy from environment.

    Expected:
        socks5://USERNAME:PASSWORD@HOST:PORT

    Example:
        socks5://myuser:mypass@185.221.237.197:1080
    """

    proxy_url = os.getenv("SOCKS5_PROXY_URL", "").strip()

    # -----------------------------------------------------
    # Proxy variable does not exist
    # -----------------------------------------------------

    if not proxy_url:
        logger.error(
            "SOCKS5_PROXY_URL is NOT SET."
        )
        logger.error(
            "Telegram will try to connect WITHOUT proxy."
        )

        return None

    # -----------------------------------------------------
    # Parse proxy URL
    # -----------------------------------------------------

    try:
        parsed = urlparse(proxy_url)

        scheme = parsed.scheme.lower()

        if scheme not in ("socks5", "socks5h"):
            raise ValueError(
                "SOCKS5_PROXY_URL must start with "
                "socks5:// or socks5h://"
            )

        hostname = parsed.hostname
        port = parsed.port

        if not hostname:
            raise ValueError(
                "Proxy hostname is missing."
            )

        if not port:
            raise ValueError(
                "Proxy port is missing."
            )

        username = (
            unquote(parsed.username)
            if parsed.username
            else None
        )

        password = (
            unquote(parsed.password)
            if parsed.password
            else None
        )

        proxy = {
            "scheme": "socks5",
            "hostname": hostname,
            "port": port,
        }

        if username:
            proxy["username"] = username

        if password:
            proxy["password"] = password

        # IMPORTANT:
        # Never print username/password.
        logger.info(
            "SOCKS5 proxy ENABLED -> %s:%s",
            hostname,
            port,
        )

        return proxy

    except Exception as e:
        logger.error(
            "Invalid SOCKS5_PROXY_URL: %s",
            e,
        )
        raise


# =========================================================
# MAIN
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
    # FFmpeg
    # -----------------------------------------------------

    ensure_ffmpeg()

    # -----------------------------------------------------
    # SOCKS5 PROXY
    # -----------------------------------------------------

    proxy = get_proxy()

    if proxy:
        logger.info(
            "Telegram clients will use SOCKS5 proxy."
        )
    else:
        logger.warning(
            "Telegram clients are running WITHOUT SOCKS5 proxy."
        )

    # =====================================================
    # BOT CLIENT
    # =====================================================

    bot = Client(
        "hexiron_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
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
        proxy=proxy,
    )

    # =====================================================
    # PYTGCallS
    # =====================================================

    calls = PyTgCalls(userbot)

    # =====================================================
    # COMMAND HANDLERS
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
        # Start Telegram Bot
        # -------------------------------------------------

        logger.info(
            "Starting Telegram Bot client..."
        )

        await bot.start()

        logger.info(
            "Telegram Bot connected successfully."
        )

        # -------------------------------------------------
        # Start Userbot / PyTgCalls
        # -------------------------------------------------

        logger.info(
            "Starting Telegram Userbot / PyTgCalls..."
        )

        await calls.start()

        logger.info(
            "HexIron Music is UP and RUNNING."
        )

        # -------------------------------------------------
        # Keep application alive
        # -------------------------------------------------

        await idle()

    finally:

        logger.info(
            "Stopping HexIron Music..."
        )

        try:
            await calls.stop()
        except Exception as e:
            logger.warning(
                "Error while stopping PyTgCalls: %s",
                e,
            )

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
```
