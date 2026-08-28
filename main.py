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

from config import API_HASH, API_ID, BOT_TOKEN, STRING_SESSION, validate_config
from database import init_db
from handlers.admin import on_added_to_group, panel, start
from handlers.player import on_stream_end, pause, play, queue_list, resume, skip, stop
from utils.ffmpeg_setup import ensure_ffmpeg


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("hexiron")


def get_proxy():
    """
    Read SOCKS5 proxy from environment variable.

    Expected format:
    socks5://USERNAME:PASSWORD@HOST:PORT

    Also supports:
    socks5://HOST:PORT
    """

    proxy_url = os.getenv("SOCKS5_PROXY_URL", "").strip()

    if not proxy_url:
        logger.warning(
            "SOCKS5_PROXY_URL is not set. "
            "Telegram connections will use the normal network."
        )
        return None

    try:
        parsed = urlparse(proxy_url)

        if parsed.scheme.lower() not in ("socks5", "socks5h"):
            raise ValueError(
                "SOCKS5_PROXY_URL must use socks5:// or socks5h://"
            )

        if not parsed.hostname or not parsed.port:
            raise ValueError(
                "SOCKS5_PROXY_URL must contain HOST and PORT"
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

        logger.info(
            "SOCKS5 proxy enabled: %s:%s",
            parsed.hostname,
            parsed.port,
        )

        return proxy

    except Exception as e:
        logger.error("Invalid SOCKS5_PROXY_URL: %s", e)
        raise


async def run():
    validate_config()
    init_db()
    ensure_ffmpeg()

    # ---------------------------------------------------------
    # SOCKS5 PROXY
    # ---------------------------------------------------------
    proxy = get_proxy()

    # ---------------------------------------------------------
    # BOT CLIENT
    # ---------------------------------------------------------
    # This bot handles visible commands such as:
    # /start
    # /play
    # /admin
    # /pause
    # /resume
    # /skip
    # /stop
    # /queue
    # ---------------------------------------------------------
    bot = Client(
        "hexiron_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        proxy=proxy,
    )

    # ---------------------------------------------------------
    # USERBOT CLIENT
    # ---------------------------------------------------------
    # A normal Telegram user account is required for voice chats.
    # PyTgCalls uses this client.
    #
    # STRING_SESSION must belong to the user account that is
    # already a member of the groups where music will be played.
    # ---------------------------------------------------------
    userbot = Client(
        "hexiron_userbot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=STRING_SESSION,
        proxy=proxy,
    )

    calls = PyTgCalls(userbot)

    # ---------------------------------------------------------
    # COMMAND HANDLERS
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # AUTO PLAY NEXT TRACK
    # ---------------------------------------------------------

    @calls.on_update(pytgfilters.stream_end())
    async def _on_stream_end(_, update: StreamEnded):
        await on_stream_end(
            bot,
            calls,
            update.chat_id,
        )

    # ---------------------------------------------------------
    # START
    # ---------------------------------------------------------

    logger.info("HexIron Music starting...")

    try:
        # Start bot first
        await bot.start()

        # Start PyTgCalls / userbot
        await calls.start()

        logger.info("HexIron Music is up and running.")

        # Keep application alive
        await idle()

    finally:
        logger.info("Stopping HexIron Music...")

        try:
            await bot.stop()
        except Exception as e:
            logger.warning("Error while stopping bot: %s", e)


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()