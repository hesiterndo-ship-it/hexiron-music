import asyncio
import logging
import os
import subprocess

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


def _check_media_file(file_path: str) -> bool:
    """
    Verify that the downloaded media exists and FFprobe can read it.
    """
    if not file_path:
        logger.error("Media path is empty.")
        return False

    if not os.path.isfile(file_path):
        logger.error("Media file does not exist: %s", file_path)
        return False

    try:
        size = os.path.getsize(file_path)

        if size <= 0:
            logger.error("Media file is empty: %s", file_path)
            return False

        logger.info(
            "Checking media file: path=%s size=%d bytes",
            file_path,
            size,
        )

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,format_name",
                "-of",
                "default=noprint_wrappers=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(
                "FFprobe failed for %s: %s",
                file_path,
                result.stderr.strip(),
            )
            return False

        logger.info(
            "FFprobe OK for %s: %s",
            file_path,
            result.stdout.strip().replace("\n", " | "),
        )

        return True

    except Exception:
        logger.exception(
            "Unexpected error while checking media file: %s",
            file_path,
        )
        return False


def _build_stream(file_path: str) -> MediaStream:
    """
    Build an audio-only MediaStream.

    FFmpeg/FFprobe are installed in the Docker image.
    """
    logger.info(
        "Building MediaStream: %s",
        file_path,
    )

    return MediaStream(
        file_path,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE,
    )


async def _play_track(
    calls: PyTgCalls,
    chat_id: int,
    file_path: str,
) -> None:
    """
    Validate the file, create MediaStream and start playback.
    Detailed exceptions are logged so the real ntgcalls error
    appears in Liara logs.
    """

    logger.info(
        "Starting playback: chat_id=%s file=%s",
        chat_id,
        file_path,
    )

    if not _check_media_file(file_path):
        raise RuntimeError(
            "فایل صوتی توسط FFprobe قابل خواندن نیست."
        )

    try:
        stream = _build_stream(file_path)

        logger.info(
            "MediaStream created successfully: chat_id=%s",
            chat_id,
        )

        await calls.play(
            chat_id,
            stream,
        )

        logger.info(
            "calls.play() completed successfully: chat_id=%s",
            chat_id,
        )

    except Exception:
        logger.exception(
            "PyTgCalls playback failed: chat_id=%s file=%s",
            chat_id,
            file_path,
        )
        raise


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

    if not await is_group_licensed(message.chat.id):
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

    query = message.text.split(None, 1)[1]

    status = await message.reply_text(
        f"🔎 در حال جستجو: {query}"
    )

    try:
        track = await asyncio.to_thread(
            search_and_download,
            query,
        )

    except Exception:
        logger.exception(
            "Search/download failed: query=%s",
            query,
        )

        await status.edit_text(
            "❌ خطا در جست‌وجو/دانلود."
        )
        return

    if track is None:
        await status.edit_text(
            "چیزی پیدا نشد."
        )
        return

    chat_id = message.chat.id
    file_path = track.get("file_path")

    logger.info(
        "Track found: chat_id=%s title=%s path=%s duration=%s",
        chat_id,
        track.get("title"),
        file_path,
        track.get("duration"),
    )

    if chat_id not in active_chats:
        try:
            await _play_track(
                calls,
                chat_id,
                file_path,
            )

            active_chats.add(chat_id)

            await status.edit_text(
                f"▶️ در حال پخش: {track['title']} "
                f"({format_duration(track['duration'])})"
            )

        except NoActiveGroupCall:
            logger.exception(
                "No active group call: chat_id=%s",
                chat_id,
            )

            active_chats.discard(chat_id)

            await status.edit_text(
                "❌ ویس‌چت این گروه فعال نیست. "
                "اول یک ویس‌چت در گروه شروع کن."
            )

        except Exception as e:
            logger.exception(
                "Playback error: chat_id=%s title=%s",
                chat_id,
                track.get("title"),
            )

            active_chats.discard(chat_id)

            await status.edit_text(
                f"❌ خطا در پخش: {e}"
            )

    else:
        try:
            user_id = (
                message.from_user.id
                if message.from_user
                else 0
            )

            database.add_to_queue(
                chat_id,
                track["title"],
                track["file_path"],
                user_id,
            )

            await status.edit_text(
                f"➕ به صف اضافه شد: {track['title']}"
            )

        except Exception:
            logger.exception(
                "Failed to add track to queue: chat_id=%s",
                chat_id,
            )

            await status.edit_text(
                "❌ خطا در اضافه کردن آهنگ به صف."
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
            "Pause failed: chat_id=%s",
            message.chat.id,
        )

        await message.reply_text(
            f"❌ {e}"
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
            "Resume failed: chat_id=%s",
            message.chat.id,
        )

        await message.reply_text(
            f"❌ {e}"
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
            logger.exception(
                "Failed to leave call after empty queue: chat_id=%s",
                chat_id,
            )

        active_chats.discard(chat_id)

        await message.reply_text(
            "⏭ صف خالی است، از ویس‌چت خارج شدم."
        )
        return

    try:
        await _play_track(
            calls,
            chat_id,
            nxt["file_path"],
        )

        active_chats.add(chat_id)

        await message.reply_text(
            f"⏭ در حال پخش: {nxt['title']}"
        )

    except Exception as e:
        logger.exception(
            "Skip playback failed: chat_id=%s file=%s",
            chat_id,
            nxt.get("file_path"),
        )

        active_chats.discard(chat_id)

        await message.reply_text(
            f"❌ خطا در پخش: {e}"
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
        logger.exception(
            "Leave call failed during stop: chat_id=%s",
            chat_id,
        )

    active_chats.discard(chat_id)

    try:
        database.clear_queue(chat_id)
    except Exception:
        logger.exception(
            "Failed to clear queue: chat_id=%s",
            chat_id,
        )

    await message.reply_text(
        "⏹ پخش متوقف شد و صف پاک شد."
    )


async def queue_list(
    client: Client,
    message: Message,
):
    try:
        titles = database.peek_queue(
            message.chat.id
        )

    except Exception:
        logger.exception(
            "Queue lookup failed: chat_id=%s",
            message.chat.id,
        )

        await message.reply_text(
            "❌ خطا در دریافت صف."
        )
        return

    if not titles:
        await message.reply_text(
            "صف خالی است."
        )
        return

    text = (
        "📜 صف پخش:\n"
        + "\n".join(
            f"{i + 1}. {t}"
            for i, t in enumerate(titles)
        )
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
    Called by main.py when a track finishes.
    """

    logger.info(
        "Stream ended: chat_id=%s",
        chat_id,
    )

    try:
        nxt = database.pop_next(chat_id)

    except Exception:
        logger.exception(
            "Failed to get next track: chat_id=%s",
            chat_id,
        )

        active_chats.discard(chat_id)
        return

    if nxt is None:
        logger.info(
            "Queue empty after stream end: chat_id=%s",
            chat_id,
        )

        active_chats.discard(chat_id)

        try:
            await calls.leave_call(
                chat_id
            )
        except Exception:
            logger.exception(
                "Failed to leave call after stream end: chat_id=%s",
                chat_id,
            )

        return

    try:
        await _play_track(
            calls,
            chat_id,
            nxt["file_path"],
        )

        active_chats.add(chat_id)

        logger.info(
            "Next queued track started: chat_id=%s title=%s",
            chat_id,
            nxt.get("title"),
        )

    except Exception:
        logger.exception(
            "Failed to play next queued track: chat_id=%s file=%s",
            chat_id,
            nxt.get("file_path"),
        )

        active_chats.discard(chat_id)