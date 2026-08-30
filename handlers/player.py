import asyncio
import logging
import os

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


logger = logging.getLogger("hexiron.player")


# chat_id -> bool
active_chats = set()

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def _build_stream(file_path: str) -> MediaStream:
    """
    Build an audio-only MediaStream.

    RadioJavan files are downloaded as M4A/AAC.
    FFmpeg is used by ntgcalls to decode them.
    """

    if not file_path:
        raise ValueError("مسیر فایل خالی است.")

    file_path = os.path.abspath(file_path)

    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"فایل آهنگ پیدا نشد: {file_path}"
        )

    file_size = os.path.getsize(file_path)

    if file_size <= 0:
        raise ValueError(
            f"فایل آهنگ خالی است: {file_path}"
        )

    logger.info(
        "Building audio stream: %s (%d bytes)",
        file_path,
        file_size,
    )

    return MediaStream(
        file_path,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE,
        ffmpeg_parameters=(
            "-vn "
            "-ac 2 "
            "-ar 48000 "
            "-f s16le"
        ),
    )


async def _safe_edit(message: Message, text: str):
    try:
        await message.edit_text(text)
    except Exception:
        pass


async def play(
    client: Client,
    message: Message,
    calls: PyTgCalls,
):
    if message.chat.type not in GROUP_TYPES:
        await message.reply_text(
            "این دستور فقط داخل گروه کار می‌کند."
        )
        return

    chat_id = message.chat.id

    if not await is_group_licensed(chat_id):
        buy_hint = (
            f"@{CENTRAL_BOT_USERNAME}"
            if CENTRAL_BOT_USERNAME
            else "ربات فروش"
        )

        await message.reply_text(
            "🚫 این گروه لایسنس فعال موزیک نداره.\n"
            f"برای خرید/تمدید: توی پیوی {buy_hint} بزن /shop"
        )
        return

    if len(message.command) < 2:
        await message.reply_text(
            "استفاده: /play <اسم آهنگ>"
        )
        return

    query = message.text.split(None, 1)[1].strip()

    if not query:
        await message.reply_text(
            "اسم آهنگ را وارد کن."
        )
        return

    status = await message.reply_text(
        f"🔎 در حال جستجو: {query}"
    )

    # --------------------------------------------------
    # SEARCH + DOWNLOAD
    # --------------------------------------------------

    try:
        track = await asyncio.to_thread(
            search_and_download,
            query,
        )

    except Exception as e:
        logger.exception(
            "Search/download failed for %r",
            query,
        )

        await _safe_edit(
            status,
            f"❌ خطا در جست‌وجو/دانلود:\n{e}",
        )
        return

    if track is None:
        await _safe_edit(
            status,
            "❌ چیزی پیدا نشد.",
        )
        return

    file_path = track.get("file_path")

    if not file_path:
        await _safe_edit(
            status,
            "❌ مسیر فایل آهنگ دریافت نشد.",
        )
        return

    logger.info(
        "Track selected: title=%r path=%r duration=%r",
        track.get("title"),
        file_path,
        track.get("duration"),
    )

    # --------------------------------------------------
    # QUEUE
    # --------------------------------------------------

    if chat_id in active_chats:
        try:
            user_id = (
                message.from_user.id
                if message.from_user
                else 0
            )

            database.add_to_queue(
                chat_id,
                track["title"],
                file_path,
                user_id,
            )

            await _safe_edit(
                status,
                f"➕ به صف اضافه شد:\n{track['title']}",
            )

        except Exception as e:
            logger.exception(
                "Queue error for chat %s",
                chat_id,
            )

            await _safe_edit(
                status,
                f"❌ خطا در اضافه کردن به صف:\n{e}",
            )

        return

    # --------------------------------------------------
    # START PLAYBACK
    # --------------------------------------------------

    try:
        stream = _build_stream(file_path)

        logger.info(
            "Starting playback in chat %s: %s",
            chat_id,
            file_path,
        )

        await calls.play(
            chat_id,
            stream,
        )

        active_chats.add(chat_id)

        logger.info(
            "Playback started successfully in chat %s",
            chat_id,
        )

        duration = track.get("duration", 0)

        await _safe_edit(
            status,
            f"▶️ در حال پخش:\n"
            f"{track['title']} "
            f"({format_duration(duration)})",
        )

    except NoActiveGroupCall:
        active_chats.discard(chat_id)

        logger.warning(
            "No active group call in chat %s",
            chat_id,
        )

        await _safe_edit(
            status,
            "❌ ویس‌چت این گروه فعال نیست.\n"
            "اول یک ویس‌چت در گروه شروع کن.",
        )

    except Exception as e:
        active_chats.discard(chat_id)

        logger.exception(
            "Playback failed in chat %s",
            chat_id,
        )

        await _safe_edit(
            status,
            f"❌ خطا در پخش:\n{type(e).__name__}: {e}",
        )


async def pause(
    client: Client,
    message: Message,
    calls: PyTgCalls,
):
    try:
        await calls.pause(
            message.chat.id
        )

        await message.reply_text(
            "⏸ متوقف شد."
        )

    except Exception as e:
        logger.exception(
            "Pause failed",
        )

        await message.reply_text(
            f"❌ خطا در توقف موقت:\n{e}"
        )


async def resume(
    client: Client,
    message: Message,
    calls: PyTgCalls,
):
    try:
        await calls.resume(
            message.chat.id
        )

        await message.reply_text(
            "▶️ ادامه یافت."
        )

    except Exception as e:
        logger.exception(
            "Resume failed",
        )

        await message.reply_text(
            f"❌ خطا در ادامه پخش:\n{e}"
        )


async def skip(
    client: Client,
    message: Message,
    calls: PyTgCalls,
):
    chat_id = message.chat.id

    nxt = database.pop_next(chat_id)

    if nxt is None:
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass

        active_chats.discard(chat_id)

        await message.reply_text(
            "⏭ صف خالی است، از ویس‌چت خارج شدم."
        )
        return

    try:
        stream = _build_stream(
            nxt["file_path"]
        )

        await calls.play(
            chat_id,
            stream,
        )

        active_chats.add(chat_id)

        await message.reply_text(
            f"⏭ در حال پخش:\n{nxt['title']}"
        )

    except Exception as e:
        active_chats.discard(chat_id)

        logger.exception(
            "Skip playback failed in chat %s",
            chat_id,
        )

        await message.reply_text(
            f"❌ خطا در پخش آهنگ بعدی:\n{type(e).__name__}: {e}"
        )


async def stop(
    client: Client,
    message: Message,
    calls: PyTgCalls,
):
    chat_id = message.chat.id

    try:
        await calls.leave_call(
            chat_id
        )
    except Exception:
        pass

    active_chats.discard(chat_id)

    try:
        database.clear_queue(chat_id)
    except Exception:
        logger.exception(
            "Failed to clear queue for chat %s",
            chat_id,
        )

    await message.reply_text(
        "⏹ پخش متوقف شد و صف پاک شد."
    )


async def queue_list(
    client: Client,
    message: Message,
):
    titles = database.peek_queue(
        message.chat.id
    )

    if not titles:
        await message.reply_text(
            "صف خالی است."
        )
        return

    text = "📜 صف پخش:\n"

    text += "\n".join(
        f"{i + 1}. {title}"
        for i, title in enumerate(titles)
    )

    await message.reply_text(
        text
    )


async def on_stream_end(
    client: Client,
    calls: PyTgCalls,
    chat_id: int,
):
    """
    Called when the current stream ends.
    """

    logger.info(
        "Stream ended in chat %s",
        chat_id,
    )

    nxt = database.pop_next(
        chat_id
    )

    if nxt is None:
        active_chats.discard(chat_id)

        try:
            await calls.leave_call(
                chat_id
            )
        except Exception:
            pass

        logger.info(
            "Queue empty; left chat %s",
            chat_id,
        )

        return

    try:
        stream = _build_stream(
            nxt["file_path"]
        )

        await calls.play(
            chat_id,
            stream,
        )

        active_chats.add(chat_id)

        logger.info(
            "Next track started in chat %s: %s",
            chat_id,
            nxt["title"],
        )

    except Exception as e:
        active_chats.discard(chat_id)

        logger.exception(
            "Failed to play next track in chat %s",
            chat_id,
        )