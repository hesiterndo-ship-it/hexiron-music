import asyncio

from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.exceptions import NoActiveGroupCall
from pytgcalls.types import MediaStream
from pytgcalls.types.stream import AudioQuality

import database
from music.downloader import search_and_download
from utils.helpers import format_duration
from utils.license_client import is_group_licensed
from config import CENTRAL_BOT_USERNAME

# chat_id -> bool, tracks whether something is currently playing so we know
# whether a new /play should start immediately or join the queue.
active_chats = set()

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def _build_stream(file_path: str) -> MediaStream:
    return MediaStream(
        file_path,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE,
    )


async def play(client: Client, message: Message, calls: PyTgCalls):
    if message.chat.type not in GROUP_TYPES:
        await message.reply_text("این دستور فقط داخل گروه کار می‌کند.")
        return

    if not await is_group_licensed(message.chat.id):
        buy_hint = f"@{CENTRAL_BOT_USERNAME}" if CENTRAL_BOT_USERNAME else "ربات فروش"
        await message.reply_text(
            "🚫 این گروه لایسنس فعال موزیک نداره.\n"
            f"برای خرید/تمدید: توی پیوی {buy_hint} بزن /shop"
        )
        return

    if len(message.command) < 2:
        await message.reply_text("استفاده: /play <اسم آهنگ>")
        return

    query = message.text.split(None, 1)[1]
    status = await message.reply_text(f"🔎 در حال جستجو: {query}")

    try:
        track = search_and_download(query)
    except Exception as e:
        await status.edit_text(f"❌ خطا در جست‌وجو/دانلود: {e}")
        return

    if track is None:
        await status.edit_text("چیزی پیدا نشد.")
        return

    chat_id = message.chat.id

    if chat_id not in active_chats:
        try:
            await calls.play(chat_id, _build_stream(track["file_path"]))
            active_chats.add(chat_id)
            await status.edit_text(
                f"▶️ در حال پخش: {track['title']} "
                f"({format_duration(track['duration'])})"
            )
        except NoActiveGroupCall:
            await status.edit_text(
                "❌ ویس‌چت این گروه فعال نیست. اول یک ویس‌چت در گروه شروع کن."
            )
        except Exception as e:
            await status.edit_text(f"❌ خطا در پخش: {e}")
    else:
        database.add_to_queue(
            chat_id, track["title"], track["file_path"], message.from_user.id
        )
        await status.edit_text(f"➕ به صف اضافه شد: {track['title']}")


async def pause(client: Client, message: Message, calls: PyTgCalls):
    try:
        await calls.pause(message.chat.id)
        await message.reply_text("⏸ متوقف شد.")
    except Exception as e:
        await message.reply_text(f"❌ {e}")


async def resume(client: Client, message: Message, calls: PyTgCalls):
    try:
        await calls.resume(message.chat.id)
        await message.reply_text("▶️ ادامه یافت.")
    except Exception as e:
        await message.reply_text(f"❌ {e}")


async def skip(client: Client, message: Message, calls: PyTgCalls):
    chat_id = message.chat.id
    nxt = database.pop_next(chat_id)
    if nxt is None:
        await calls.leave_call(chat_id)
        active_chats.discard(chat_id)
        await message.reply_text("⏭ صف خالی است، از ویس‌چت خارج شدم.")
        return

    try:
        await calls.play(chat_id, _build_stream(nxt["file_path"]))
        await message.reply_text(f"⏭ در حال پخش: {nxt['title']}")
    except Exception as e:
        await message.reply_text(f"❌ {e}")


async def stop(client: Client, message: Message, calls: PyTgCalls):
    chat_id = message.chat.id
    try:
        await calls.leave_call(chat_id)
    except Exception:
        pass
    active_chats.discard(chat_id)
    database.clear_queue(chat_id)
    await message.reply_text("⏹ پخش متوقف شد و صف پاک شد.")


async def queue_list(client: Client, message: Message):
    titles = database.peek_queue(message.chat.id)
    if not titles:
        await message.reply_text("صف خالی است.")
        return
    text = "📜 صف پخش:\n" + "\n".join(
        f"{i+1}. {t}" for i, t in enumerate(titles)
    )
    await message.reply_text(text)


async def on_stream_end(client: Client, calls: PyTgCalls, chat_id: int):
    """Called by main.py when a track finishes: auto-play the next queued
    track, or leave the call if the queue is empty."""
    nxt = database.pop_next(chat_id)
    if nxt is None:
        active_chats.discard(chat_id)
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass
        return

    try:
        await calls.play(chat_id, _build_stream(nxt["file_path"]))
    except Exception:
        active_chats.discard(chat_id)
