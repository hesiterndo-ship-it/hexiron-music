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


def get_telegram_proxy():
    proxy_url = os.getenv("SOCKS5_PROXY_URL")

    if not proxy_url:
        logger.info(
            "Telegram SOCKS5 proxy is not configured; using direct connection."
        )
        return None

    parsed = urlparse(proxy_url)

    if parsed.scheme.lower() not in ("socks5", "socks5h", "socks"):
        raise ValueError(
            f"Unsupported SOCKS5 proxy scheme: {parsed.scheme}"
        )

    if not parsed.hostname or not parsed.port:
        raise ValueError(
            "SOCKS5_PROXY_URL must contain hostname and port."
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
        "Telegram SOCKS5 proxy enabled: %s:%s",
        parsed.hostname,
        parsed.port,
    )

    return proxy


async def run():
    validate_config()
    init_db()
    ensure_ffmpeg()

    telegram_proxy = get_telegram_proxy()

    bot = Client(
        "hexiron_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        proxy=telegram_proxy,
    )

    userbot = Client(
        "hexiron_userbot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=STRING_SESSION,
        proxy=telegram_proxy,
    )

    calls = PyTgCalls(userbot)

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

    @calls.on_update(pytgfilters.stream_end())
    async def _on_stream_end(_, update: StreamEnded):
        await on_stream_end(bot, calls, update.chat_id)

    logger.info("HexIron Music starting...")

    await bot.start()
    await calls.start()

    logger.info("HexIron Music is up and running.")

    await idle()

    await bot.stop()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
