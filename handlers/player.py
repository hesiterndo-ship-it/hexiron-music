"""
Music player handlers: play, pause, resume, skip, stop, queue, upload, search.

This is the core playback engine.  It uses PyTgCalls for voice chat and
integrates with the per-chat PlayerState, database queue, control panel,
and the new modular source system (music.sources).
"""

import asyncio
import logging
import os
import time
from typing import Optional

from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import Message

from pytgcalls import PyTgCalls
from pytgcalls.exceptions import NoActiveGroupCall
from pytgcalls.types import MediaStream
from pytgcalls.types.stream import AudioQuality

import database
from config import (
    MAX_QUEUE_SIZE,
    MAX_UPLOAD_SIZE_MB,
    CENTRAL_BOT_USERNAME,
    UPLOAD_DIR,
)
from music.sources.router import (
    detect_source,
    search_and_download_music,
)
from music.sources.item import MusicItem
from services.player_state import LoopMode, NowPlaying, get_state
from services.permissions import (
    can_upload,
    get_user_name,
    register_user_from_message,
)
from utils.helpers import escape_html, format_duration, sanitize_filename
from utils.license_client import is_group_licensed

logger = logging.getLogger("hexiron.player")

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)

# chat_id -> bool (legacy compat — kept for quick checks)
active_chats = set()


# ── Stream builder ───────────────────────────────────────────────────


def _build_stream(file_path: str) -> MediaStream:
    """Build an audio-only MediaStream for PyTgCalls."""
    if not file_path:
        raise ValueError("File path is empty")

    file_path = os.path.abspath(file_path)

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = os.path.getsize(file_path)
    if file_size <= 0:
        raise ValueError(f"File is empty: {file_path}")

    logger.info("Building audio stream: %s (%d bytes)", file_path, file_size)

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
    """Edit a message, ignoring errors."""
    try:
        await message.edit_text(text)
    except Exception:
        pass


# ── Play a file directly ─────────────────────────────────────────────


async def play_file(
    client: Client,
    message: Message,
    calls: PyTgCalls,
    chat_id: int,
    file_path: str,
    title: str,
    artist: str = "",
    duration: int = 0,
    requested_by: int = 0,
    requested_by_name: str = "",
    status_message: Optional[Message] = None,
    source: str = "unknown",
    source_url: str = "",
):
    """
    Play a file in a chat's voice chat.  If already playing, queue it.
    """
    state = get_state(chat_id)

    if chat_id in active_chats and state.is_playing:
        # Add to queue
        qlen = database.queue_length(chat_id)
        if qlen >= MAX_QUEUE_SIZE:
            if status_message:
                await _safe_edit(
                    status_message,
                    f"❌ Queue is full (max {MAX_QUEUE_SIZE} songs).",
                )
            return

        database.add_to_queue(
            chat_id, title, file_path, requested_by,
            artist=artist, duration=duration,
            source=source,
        )

        position = database.queue_length(chat_id)
        if status_message:
            await _safe_edit(
                status_message,
                f"➕ Added to Queue\n\n"
                f"🎵 {escape_html(title)}\n"
                f"👤 {escape_html(artist)}\n"
                f"⏱ {format_duration(duration)}\n\n"
                f"Position: #{position}\n"
                f"👤 Requested by: {escape_html(requested_by_name)}",
            )
        return

    # Start playback
    try:
        stream = _build_stream(file_path)
        await calls.play(chat_id, stream)

        active_chats.add(chat_id)
        state.is_playing = True
        state.is_paused = False
        state.now_playing = NowPlaying(
            title=title,
            artist=artist,
            duration=duration,
            file_path=file_path,
            source=source,
            source_url=source_url,
            requested_by=requested_by,
            requested_by_name=requested_by_name,
            started_at=time.time(),
        )

        # Persist settings
        db_settings = database.get_chat_settings(chat_id)
        state.volume = db_settings.get("default_volume", 100)
        state.loop_mode = LoopMode(db_settings.get("loop_mode", "off"))
        state.shuffle_enabled = bool(db_settings.get("shuffle", 0))

        # Update stats
        database.incr_stat("songs_played")

        if status_message:
            from handlers.control_panel import send_or_update_panel
            panel_id = await send_or_update_panel(client, chat_id)
            state.player_message_id = panel_id

        logger.info("Playback started in chat %s: %s", chat_id, title)

    except NoActiveGroupCall:
        active_chats.discard(chat_id)
        state.is_playing = False
        state.now_playing = None
        if status_message:
            await _safe_edit(
                status_message,
                "❌ No active voice chat.\n"
                "Start a voice chat in the group first.",
            )

    except Exception as e:
        active_chats.discard(chat_id)
        state.is_playing = False
        state.now_playing = None
        logger.exception("Playback failed in chat %s", chat_id)
        if status_message:
            await _safe_edit(
                status_message,
                f"❌ Playback error: {type(e).__name__}: {e}",
            )


async def play_music_item(
    client: Client,
    message: Message,
    calls: PyTgCalls,
    chat_id: int,
    item: MusicItem,
    status_message: Optional[Message] = None,
):
    """Convenience: play a MusicItem."""
    await play_file(
        client, message, calls, chat_id,
        file_path=item.local_path,
        title=item.title,
        artist=item.artist,
        duration=item.duration,
        requested_by=item.requested_by,
        requested_by_name=item.requested_by_name,
        status_message=status_message,
        source=item.source,
        source_url=item.source_url,
    )


# ── /play command ────────────────────────────────────────────────────


async def play(client: Client, message: Message, calls: PyTgCalls):
    register_user_from_message(message)

    if message.chat.type not in GROUP_TYPES:
        await message.reply_text("This command only works in groups.")
        return

    chat_id = message.chat.id

    if not await is_group_licensed(chat_id):
        buy_hint = (
            f"@{CENTRAL_BOT_USERNAME}"
            if CENTRAL_BOT_USERNAME
            else "the sales bot"
        )
        await message.reply_text(
            "🚫 This group doesn't have an active music license.\n"
            f"To purchase/renew: DM {buy_hint} and use /shop"
        )
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: /play <song name or URL>")
        return

    query = message.text.split(None, 1)[1].strip()
    if not query:
        await message.reply_text("Enter a song name or URL.")
        return

    user_id = message.from_user.id if message.from_user else 0
    user_name = get_user_name(message.from_user)

    source = detect_source(query)
    source_label = {"youtube": "YouTube", "tiktok": "TikTok", "generic": "URL"}.get(source, "search")
    status = await message.reply_text(f"🔎 Searching ({source_label}): {query}")

    # Search and download via the provider system
    try:
        item = await asyncio.to_thread(
            _blocking_search_download, query, user_id, user_name
        )
    except Exception as e:
        logger.exception("Search/download failed for %r", query)
        await _safe_edit(status, f"❌ Search/download error:\n{e}")
        return

    if item is None:
        await _safe_edit(status, "❌ No results found.")
        return

    if not item.local_path:
        await _safe_edit(status, "❌ Track file path not available.")
        return

    await play_music_item(
        client, message, calls, chat_id, item,
        status_message=status,
    )


def _blocking_search_download(query: str, user_id: int, user_name: str) -> Optional[MusicItem]:
    """Blocking wrapper for asyncio.to_thread."""
    return asyncio.run(
        search_and_download_music(
            query, requested_by=user_id, requested_by_name=user_name
        )
    )


# ── /play with uploaded audio ────────────────────────────────────────


async def handle_audio_upload(client: Client, message: Message, calls: PyTgCalls):
    """Handle audio files sent to the bot for playback."""
    register_user_from_message(message)

    if message.chat.type not in GROUP_TYPES:
        await message.reply_text(
            "Send audio files directly in a group to play them, "
            "or use /play <name> to search."
        )
        return

    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    user_name = get_user_name(message.from_user)

    if not can_upload(user_id, chat_id):
        await message.reply_text("⛔️ You don't have permission to upload music here.")
        return

    if not await is_group_licensed(chat_id):
        buy_hint = (
            f"@{CENTRAL_BOT_USERNAME}"
            if CENTRAL_BOT_USERNAME
            else "the sales bot"
        )
        await message.reply_text(
            "🚫 This group doesn't have an active music license.\n"
            f"To purchase/renew: DM {buy_hint} and use /shop"
        )
        return

    # Determine which media to use
    audio = message.audio or message.document
    if not audio:
        await message.reply_text("Please send an audio file.")
        return

    # Check file size
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if audio.file_size and audio.file_size > max_bytes:
        await message.reply_text(
            f"❌ File too large. Maximum size: {MAX_UPLOAD_SIZE_MB} MB."
        )
        return

    # Check format
    supported_exts = {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".wma"}
    file_name = audio.file_name or "uploaded_audio"
    ext = os.path.splitext(file_name)[1].lower()

    if ext and ext not in supported_exts:
        await message.reply_text(
            f"❌ Unsupported format: {ext}\n"
            f"Supported: {', '.join(supported_exts)}"
        )
        return

    status = await message.reply_text("📥 Downloading audio file...")

    try:
        safe_name = sanitize_filename(os.path.splitext(file_name)[0])
        dest = os.path.join(
            UPLOAD_DIR,
            f"upload_{user_id}_{safe_name}{ext or '.mp3'}",
        )

        await message.download_file(dest)

        if not os.path.exists(dest) or os.path.getsize(dest) == 0:
            await _safe_edit(status, "❌ Download failed or file is empty.")
            return

        # Extract metadata from Telegram
        title = safe_name
        artist = ""
        duration = 0

        if message.audio:
            if message.audio.title:
                title = message.audio.title
            if message.audio.performer:
                artist = message.audio.performer
            if message.audio.duration:
                duration = message.audio.duration

        await _safe_edit(
            status,
            f"🎵 <b>Added to Queue</b>\n\n"
            f"Title: {escape_html(title)}\n"
            f"Artist: {escape_html(artist or 'Unknown')}\n"
            f"⏱ Duration: {format_duration(duration)}\n\n"
            f"👤 Requested by: {escape_html(user_name)}",
        )

        await play_file(
            client, message, calls, chat_id,
            file_path=dest,
            title=title,
            artist=artist,
            duration=duration,
            requested_by=user_id,
            requested_by_name=user_name,
            status_message=None,
            source="telegram",
        )

    except Exception as e:
        logger.exception("Upload handling failed")
        await _safe_edit(status, f"❌ Upload error: {e}")


# ── /pause ───────────────────────────────────────────────────────────


async def pause(client: Client, message: Message, calls: PyTgCalls):
    chat_id = message.chat.id
    state = get_state(chat_id)

    if not state.is_playing or state.is_paused:
        await message.reply_text("Nothing to pause.")
        return

    try:
        await calls.pause(chat_id)
        state.is_paused = True
        await message.reply_text("⏸ Paused")
    except Exception as e:
        logger.exception("Pause failed")
        await message.reply_text(f"❌ Pause error: {e}")


# ── /resume ──────────────────────────────────────────────────────────


async def resume(client: Client, message: Message, calls: PyTgCalls):
    chat_id = message.chat.id
    state = get_state(chat_id)

    if not state.is_paused:
        await message.reply_text("Not paused.")
        return

    try:
        await calls.resume(chat_id)
        state.is_paused = False
        await message.reply_text("▶️ Resumed")
    except Exception as e:
        logger.exception("Resume failed")
        await message.reply_text(f"❌ Resume error: {e}")


# ── skip_track (also callable from control panel) ────────────────────


async def skip_track(
    client: Client,
    message: Message,
    calls: PyTgCalls,
    chat_id: int,
):
    """Skip current track and play next from queue."""
    state = get_state(chat_id)

    # Check loop mode
    if state.loop_mode == LoopMode.CURRENT and state.now_playing:
        try:
            stream = _build_stream(state.now_playing.file_path)
            await calls.play(chat_id, stream)
            state.now_playing.started_at = time.time()
            from handlers.control_panel import send_or_update_panel
            await send_or_update_panel(client, chat_id, state.player_message_id)
            return
        except Exception as e:
            logger.exception("Replay failed in chat %s", chat_id)

    # Pop next from queue
    nxt = database.pop_next(chat_id)

    if nxt is None:
        # Queue empty
        if state.loop_mode == LoopMode.QUEUE and state.now_playing:
            try:
                stream = _build_stream(state.now_playing.file_path)
                await calls.play(chat_id, stream)
                state.now_playing.started_at = time.time()
                from handlers.control_panel import send_or_update_panel
                await send_or_update_panel(client, chat_id, state.player_message_id)
                return
            except Exception:
                pass

        active_chats.discard(chat_id)
        state.is_playing = False
        state.is_paused = False
        state.now_playing = None

        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass

        await message.reply_text("⏭ Queue finished. No more songs.")
        return

    # Play next track
    try:
        stream = _build_stream(nxt["file_path"])
        await calls.play(chat_id, stream)

        active_chats.add(chat_id)
        state.is_playing = True
        state.is_paused = False

        req_user = database.get_user(nxt.get("requested_by", 0))
        req_name = req_user["full_name"] if req_user else str(nxt.get("requested_by", ""))

        state.now_playing = NowPlaying(
            title=nxt["title"],
            artist=nxt.get("artist", ""),
            duration=nxt.get("duration", 0),
            file_path=nxt["file_path"],
            source=nxt.get("source", "unknown"),
            source_url=nxt.get("source_url", ""),
            requested_by=nxt.get("requested_by", 0),
            requested_by_name=req_name,
            started_at=time.time(),
        )

        from handlers.control_panel import send_or_update_panel
        await send_or_update_panel(client, chat_id, state.player_message_id)

    except Exception as e:
        active_chats.discard(chat_id)
        state.is_playing = False
        state.now_playing = None
        logger.exception("Skip playback failed in chat %s", chat_id)
        await message.reply_text(
            f"❌ Error playing next track:\n{type(e).__name__}: {e}"
        )


async def skip(client: Client, message: Message, calls: PyTgCalls):
    await skip_track(client, message, calls, message.chat.id)


# ── stop_playback (also callable from control panel) ──────────────────


async def stop_playback(
    client: Client,
    message: Message,
    calls: PyTgCalls,
    chat_id: int,
):
    """Stop playback, clear queue, leave voice chat."""
    state = get_state(chat_id)

    try:
        await calls.leave_call(chat_id)
    except Exception:
        pass

    active_chats.discard(chat_id)
    state.is_playing = False
    state.is_paused = False
    state.now_playing = None

    try:
        database.clear_queue(chat_id)
    except Exception:
        logger.exception("Failed to clear queue for chat %s", chat_id)

    if state.player_message_id:
        try:
            await client.delete_messages(chat_id, state.player_message_id)
        except Exception:
            pass
        state.player_message_id = 0

    await message.reply_text("⏹ Playback stopped and queue cleared.")


async def stop(client: Client, message: Message, calls: PyTgCalls):
    await stop_playback(client, message, calls, message.chat.id)


# ── /queue display ───────────────────────────────────────────────────


async def queue_list(client: Client, message: Message):
    register_user_from_message(message)
    chat_id = message.chat.id

    queue_items = database.peek_queue(chat_id)

    if not queue_items:
        await message.reply_text("📜 Queue is empty.")
        return

    from handlers.control_panel import build_queue_keyboard, _build_queue_text

    text = _build_queue_text(chat_id, 0)
    keyboard = build_queue_keyboard(chat_id, 0)

    await message.reply_text(text, reply_markup=keyboard)


# ── on_stream_end (auto-advance) ─────────────────────────────────────


async def on_stream_end(client: Client, calls: PyTgCalls, chat_id: int):
    """Called when the current stream finishes. Auto-advance to next track."""
    state = get_state(chat_id)

    logger.info("Stream ended in chat %s", chat_id)

    # Handle loop modes
    if state.loop_mode == LoopMode.CURRENT and state.now_playing:
        try:
            stream = _build_stream(state.now_playing.file_path)
            await calls.play(chat_id, stream)
            state.now_playing.started_at = time.time()
            state.is_playing = True
            from handlers.control_panel import send_or_update_panel
            await send_or_update_panel(client, chat_id, state.player_message_id)
            logger.info("Replayed current track in chat %s", chat_id)
            return
        except Exception as e:
            logger.exception("Replay failed in chat %s", chat_id)

    # Pop next from queue
    nxt = database.pop_next(chat_id)

    if nxt is None:
        # Queue empty — check loop queue mode
        if state.loop_mode == LoopMode.QUEUE and state.now_playing:
            try:
                stream = _build_stream(state.now_playing.file_path)
                await calls.play(chat_id, stream)
                state.now_playing.started_at = time.time()
                state.is_playing = True
                from handlers.control_panel import send_or_update_panel
                await send_or_update_panel(client, chat_id, state.player_message_id)
                return
            except Exception:
                pass

        # Really done
        active_chats.discard(chat_id)
        state.is_playing = False
        state.is_paused = False
        state.now_playing = None

        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass

        try:
            from handlers.control_panel import send_or_update_panel
            await send_or_update_panel(client, chat_id, state.player_message_id)
        except Exception:
            pass

        logger.info("Queue empty; left chat %s", chat_id)
        return

    # Play next track
    try:
        stream = _build_stream(nxt["file_path"])
        await calls.play(chat_id, stream)

        active_chats.add(chat_id)
        state.is_playing = True
        state.is_paused = False

        req_user = database.get_user(nxt.get("requested_by", 0))
        req_name = req_user["full_name"] if req_user else str(nxt.get("requested_by", ""))

        state.now_playing = NowPlaying(
            title=nxt["title"],
            artist=nxt.get("artist", ""),
            duration=nxt.get("duration", 0),
            file_path=nxt["file_path"],
            source=nxt.get("source", "unknown"),
            source_url=nxt.get("source_url", ""),
            requested_by=nxt.get("requested_by", 0),
            requested_by_name=req_name,
            started_at=time.time(),
        )

        database.incr_stat("songs_played")

        from handlers.control_panel import send_or_update_panel
        await send_or_update_panel(client, chat_id, state.player_message_id)

        logger.info("Next track started in chat %s: %s", chat_id, nxt["title"])

    except Exception as e:
        active_chats.discard(chat_id)
        state.is_playing = False
        state.now_playing = None
        logger.exception("Failed to play next track in chat %s", chat_id)

        try:
            await on_stream_end(client, calls, chat_id)
        except Exception:
            pass
