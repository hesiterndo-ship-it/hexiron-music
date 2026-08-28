import asyncio
import logging
from functools import partial

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


async def run():
    validate_config()
    init_db()
    ensure_ffmpeg()

    # `bot` handles visible commands (/play, /admin, etc.) — this is the
    # account users see and talk to.
    bot = Client(
        "hexiron_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )

    # Telegram bot accounts are not allowed to create/join voice chats
    # (BOT_METHOD_INVALID on phone.createGroupCall). Only a regular user
    # account can, so PyTgCalls is attached to a separate "userbot"
    # client logged in via STRING_SESSION instead of the bot token. This
    # userbot must be a member of every group where playback is used.
    userbot = Client(
        "hexiron_userbot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=STRING_SESSION,
    )
    calls = PyTgCalls(userbot)

    # --- command handlers (registered on the bot client) ---
    bot.add_handler(MessageHandler(start, filters.command("start") & filters.private))
    bot.add_handler(MessageHandler(panel, filters.command("admin")))
    bot.add_handler(
        MessageHandler(on_added_to_group, filters.new_chat_members)
    )

    # play/pause/resume/skip/stop need the `calls` client, so bind it with partial
    bot.add_handler(MessageHandler(partial(play, calls=calls), filters.command("play")))
    bot.add_handler(MessageHandler(partial(pause, calls=calls), filters.command("pause")))
    bot.add_handler(MessageHandler(partial(resume, calls=calls), filters.command("resume")))
    bot.add_handler(MessageHandler(partial(skip, calls=calls), filters.command("skip")))
    bot.add_handler(MessageHandler(partial(stop, calls=calls), filters.command("stop")))
    bot.add_handler(MessageHandler(queue_list, filters.command("queue")))

    # --- auto-play next track in queue when the current one ends ---
    @calls.on_update(pytgfilters.stream_end())
    async def _on_stream_end(_, update: StreamEnded):
        await on_stream_end(bot, calls, update.chat_id)

    logger.info("HexIron Music starting...")

    # Start the bot client first (handles commands), then the userbot's
    # PyTgCalls client (handles voice chats). calls.start() connects the
    # underlying userbot Client itself, so we never call userbot.run()
    # or userbot.start() separately.
    await bot.start()
    await calls.start()
    logger.info("HexIron Music is up and running.")
    await idle()
    await bot.stop()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
