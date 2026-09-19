"""
Interactive music control panel.

Provides the inline keyboard panel that appears in group chats with:
  - Now Playing display
  - Play / Pause / Resume / Skip / Stop
  - Queue view with pagination
  - Loop mode cycling
  - Shuffle toggle
  - Volume control
  - Favorites
  - Close panel
"""

import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import database
from services.player_state import (
    LoopMode,
    get_state,
)
from services.permissions import (
    can_control_playback,
    get_user_name,
    register_user_from_message,
)
from services.favorites import add_to_favorites
from utils.helpers import escape_html, format_duration

logger = logging.getLogger("hexiron.panel")


# ── Now Playing text builder ───────────────────────────────────────


def _build_now_playing_text(chat_id: int) -> str:
    """Build the Now Playing display text."""
    state = get_state(chat_id)

    if not state.is_playing or not state.now_playing:
        return (
            "◈─────── <b>HEXIRON MUSIC</b> ───────◈\n\n"
            "No song playing.\n"
            "Use /play &lt;song name&gt; to start, or just send an "
            "audio file 📤\n\n"
            "◈──────────────────────────────◈"
        )

    np = state.now_playing
    elapsed = format_duration(np.elapsed)
    total = format_duration(np.duration)

    # Loop label
    loop_labels = {
        LoopMode.OFF: "OFF",
        LoopMode.CURRENT: "ON (current)",
        LoopMode.QUEUE: "ON (queue)",
    }
    loop_label = loop_labels.get(state.loop_mode, "OFF")

    # Queue count
    q_len = database.queue_length(chat_id)

    # Progress bar (glass-style — filled/empty blocks)
    bar = _progress_bar(np.elapsed, np.duration)

    lines = [
        "◈─────── <b>HEXIRON MUSIC</b> ───────◈\n",
        f"🎵 <b>{escape_html(np.title)}</b>",
    ]

    if np.artist:
        lines.append(f"👤 {escape_html(np.artist)}")

    lines.append(f"\n{bar}")
    lines.append(f"⏱ {elapsed} / {total}   📡 {np.source_label}")

    if np.requested_by_name:
        lines.append(f"🙋 Requested by: {escape_html(np.requested_by_name)}")

    lines.append("")
    lines.append(
        f"🔊 {state.volume}%   "
        f"🔁 {loop_label}   "
        f"🔀 {'ON' if state.shuffle_enabled else 'OFF'}"
    )
    lines.append(f"📜 Queue: {q_len} song{'s' if q_len != 1 else ''}")
    lines.append("◈──────────────────────────────◈")

    return "\n".join(lines)


def _progress_bar(elapsed: int, duration: int, length: int = 14) -> str:
    """Render a simple glass-style progress bar using block characters."""
    if not duration:
        return "▱" * length
    ratio = max(0.0, min(1.0, elapsed / duration))
    filled = int(round(ratio * length))
    return "▰" * filled + "▱" * (length - filled)


# ── Panel keyboard builder ─────────────────────────────────────────


def _build_panel_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Build the main control panel keyboard."""
    state = get_state(chat_id)
    is_playing = state.is_playing and not state.is_paused
    is_paused = state.is_paused

    row1 = [InlineKeyboardButton("⏮ Prev", callback_data="pl:prev")]
    if is_playing:
        row1.append(InlineKeyboardButton("⏸ Pause", callback_data="pl:pause"))
    else:
        row1.append(InlineKeyboardButton("▶️ Play", callback_data="pl:resume"))
    row1.append(InlineKeyboardButton("⏭ Next", callback_data="pl:skip"))
    row1.append(InlineKeyboardButton("⏹ Stop", callback_data="pl:stop"))

    row2 = [
        InlineKeyboardButton("📜 Queue", callback_data="pl:queue"),
        InlineKeyboardButton("🎧 Info", callback_data="pl:info"),
        InlineKeyboardButton("📤 Upload", callback_data="pl:upload"),
    ]

    row3 = [
        InlineKeyboardButton("🔁 Loop", callback_data="pl:loop"),
        InlineKeyboardButton("🔀 Shuffle", callback_data="pl:shuffle"),
        InlineKeyboardButton("🤖 AI", callback_data="pl:ai"),
    ]

    row4 = [
        InlineKeyboardButton("🔇 Mute", callback_data="pl:mute"),
        InlineKeyboardButton("🔉 -", callback_data="pl:vol_down"),
        InlineKeyboardButton("🔊 +", callback_data="pl:vol_up"),
    ]

    row5 = [
        InlineKeyboardButton("❤️ Save", callback_data="pl:save_fav"),
        InlineKeyboardButton("🔄 Refresh", callback_data="pl:refresh"),
        InlineKeyboardButton("❌ Close", callback_data="pl:close"),
    ]

    return InlineKeyboardMarkup([row1, row2, row3, row4, row5])


# ── Send or update panel ───────────────────────────────────────────


async def send_or_update_panel(
    client: Client,
    chat_id: int,
    message_id: int = 0,
) -> int:
    """
    Send a new panel message or edit an existing one.
    Returns the message ID.
    """
    text = _build_now_playing_text(chat_id)
    keyboard = _build_panel_keyboard(chat_id)

    if message_id:
        try:
            msg = await client.edit_message_text(
                chat_id,
                message_id,
                text,
                reply_markup=keyboard,
            )
            return message_id
        except Exception:
            pass

    try:
        msg = await client.send_message(
            chat_id,
            text,
            reply_markup=keyboard,
        )
        return msg.id
    except Exception:
        logger.exception("Failed to send panel to chat %s", chat_id)
        return 0


# ── Queue builders ─────────────────────────────────────────────────


def _build_queue_text(chat_id: int, page: int) -> str:
    """Build the queue display text."""
    items = database.peek_queue(chat_id)
    per_page = 10
    total_pages = max(1, -(-len(items) // per_page))
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    page_items = items[start: start + per_page]

    if not items:
        return "📜 <b>QUEUE</b>\n\nQueue is empty."

    lines = [f"📜 <b>QUEUE</b>  (page {page + 1}/{total_pages})\n"]

    for i, item in enumerate(page_items):
        num = start + i + 1
        title = escape_html(item.get("title", "Unknown"))
        artist = escape_html(item.get("artist", ""))
        duration = format_duration(item.get("duration", 0))
        artist_part = f" — {artist}" if artist else ""
        lines.append(f"{num}. 🎵 {title}{artist_part} ⏱ {duration}")

    return "\n".join(lines)


def build_queue_keyboard(chat_id: int, page: int) -> InlineKeyboardMarkup:
    """Build queue navigation keyboard."""
    items = database.peek_queue(chat_id)
    per_page = 10
    total_pages = max(1, -(-len(items) // per_page))

    buttons = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"pl:qpage:{page - 1}"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton("➡️ Next", callback_data=f"pl:qpage:{page + 1}"))
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🔀 Shuffle", callback_data="pl:shuffle"),
        InlineKeyboardButton("🧹 Clear", callback_data="pl:clear_queue"),
    ])
    buttons.append([
        InlineKeyboardButton("🔙 Back", callback_data="pl:refresh"),
    ])

    return InlineKeyboardMarkup(buttons)


# ── Favorites builders ─────────────────────────────────────────────


def _build_favorites_text(favorites: list, page: int) -> str:
    """Build the favorites display text."""
    per_page = 10
    total = len(favorites)
    total_pages = max(1, -(-total // per_page))
    page = max(0, min(page, total_pages - 1))

    if not favorites:
        return (
            "❤️ <b>YOUR FAVORITES</b>\n\n"
            "No favorites yet.\n"
            "Use ❤️ button on a playing song to save it."
        )

    start = page * per_page
    page_items = favorites[start: start + per_page]

    lines = [f"❤️ <b>YOUR FAVORITES</b>  (page {page + 1}/{total_pages})\n"]

    for i, fav in enumerate(page_items):
        title = escape_html(fav.get("title", "Unknown"))
        artist = escape_html(fav.get("artist", ""))
        duration = format_duration(fav.get("duration", 0))
        num = start + i + 1
        artist_part = f"\n   👤 {artist}" if artist else ""
        lines.append(f"{num}. 🎵 {title}{artist_part}\n   ⏱ {duration}")

    return "\n".join(lines)


def build_favorites_keyboard(user_id: int, page: int) -> InlineKeyboardMarkup:
    """Build favorites navigation keyboard."""
    favorites = database.get_favorites(user_id, limit=100)
    per_page = 10
    total_pages = max(1, -(-len(favorites) // per_page))

    buttons = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"pl:fpage:{page - 1}"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton("➡️ Next", callback_data=f"pl:fpage:{page + 1}"))
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🔙 Back", callback_data="pl:refresh"),
    ])

    return InlineKeyboardMarkup(buttons)


# ── Register all panel handlers ────────────────────────────────────


def register_panel_handlers(bot: Client, calls):
    """Register all control panel callback handlers."""

    @bot.on_callback_query(filters.regex(r"^pl:(.+)$"))
    async def handle_panel_callback(client: Client, callback: CallbackQuery):
        data = callback.data.split(":", 2)
        action = data[1] if len(data) > 1 else ""
        arg = data[2] if len(data) > 2 else ""

        chat_id = callback.message.chat.id
        user_id = callback.from_user.id
        state = get_state(chat_id)

        register_user_from_message(callback)

        # ── Play / Resume ──────────────────────────────────────

        if action in ("resume", "play"):
            await callback.answer()
            if state.is_paused:
                try:
                    await calls.resume(chat_id)
                    state.is_paused = False
                    await send_or_update_panel(client, chat_id, state.player_message_id)
                except Exception as e:
                    logger.exception("Resume failed")
                    await callback.answer(f"Error: {e}", show_alert=True)
            elif not state.is_playing:
                await callback.answer("Nothing playing. Use /play <song>", show_alert=True)
            else:
                await callback.answer("Already playing")
            return

        # ── Pause ──────────────────────────────────────────────

        if action == "pause":
            await callback.answer()
            if state.is_playing and not state.is_paused:
                try:
                    await calls.pause(chat_id)
                    state.is_paused = True
                    await send_or_update_panel(client, chat_id, state.player_message_id)
                except Exception as e:
                    logger.exception("Pause failed")
                    await callback.answer(f"Error: {e}", show_alert=True)
            else:
                await callback.answer("Nothing to pause")
            return

        # ── Skip ───────────────────────────────────────────────

        if action == "skip":
            await callback.answer()
            if not can_control_playback(user_id, chat_id):
                await callback.answer("⛔️ No permission", show_alert=True)
                return
            from handlers.player import skip_track
            msg = callback.message
            await skip_track(client, msg, calls, chat_id)
            return

        # ── Previous ───────────────────────────────────────────

        if action == "prev":
            await callback.answer()
            if not can_control_playback(user_id, chat_id):
                await callback.answer("⛔️ No permission", show_alert=True)
                return
            from handlers.player import play_previous
            msg = callback.message
            await play_previous(client, msg, calls, chat_id)
            return

        # ── Upload hint ──────────────────────────────────────────

        if action == "upload":
            await callback.answer(
                "📤 Just send an audio file (MP3/M4A/WAV/OGG/FLAC) "
                "here in the group — it'll be queued automatically.",
                show_alert=True,
            )
            return

        # ── AI suggestion hint ───────────────────────────────────

        if action == "ai":
            await callback.answer()
            from services.ai_service import is_available
            if not is_available():
                await callback.answer(
                    "🤖 AI features aren't configured for this bot yet.",
                    show_alert=True,
                )
                return
            await callback.answer(
                "🤖 Type: /aiplay <how you feel or what you want to hear>\n"
                "Example: /aiplay something relaxing for studying",
                show_alert=True,
            )
            return

        # ── Stop ───────────────────────────────────────────────

        if action == "stop":
            await callback.answer()
            if not can_control_playback(user_id, chat_id):
                await callback.answer("⛔️ No permission", show_alert=True)
                return
            from handlers.player import stop_playback
            msg = callback.message
            await stop_playback(client, msg, calls, chat_id)
            return

        # ── Queue ──────────────────────────────────────────────

        if action == "queue":
            await callback.answer()
            text = _build_queue_text(chat_id, 0)
            keyboard = build_queue_keyboard(chat_id, 0)
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except Exception:
                pass
            return

        if action == "qpage":
            await callback.answer()
            page = int(arg) if arg.isdigit() else 0
            text = _build_queue_text(chat_id, page)
            keyboard = build_queue_keyboard(chat_id, page)
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except Exception:
                pass
            return

        # ── Info (Now Playing) ─────────────────────────────────

        if action == "info":
            await callback.answer()
            text = _build_now_playing_text(chat_id)
            keyboard = _build_panel_keyboard(chat_id)
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except Exception:
                pass
            return

        # ── Loop mode cycling ──────────────────────────────────

        if action == "loop":
            await callback.answer()
            if state.loop_mode == LoopMode.OFF:
                state.loop_mode = LoopMode.CURRENT
                label = "ON (current song)"
            elif state.loop_mode == LoopMode.CURRENT:
                state.loop_mode = LoopMode.QUEUE
                label = "ON (queue)"
            else:
                state.loop_mode = LoopMode.OFF
                label = "OFF"

            # Persist
            database.update_chat_setting(chat_id, "loop_mode", state.loop_mode.value)
            await send_or_update_panel(client, chat_id, state.player_message_id)
            return

        # ── Shuffle toggle ─────────────────────────────────────

        if action == "shuffle":
            await callback.answer()
            state.shuffle_enabled = not state.shuffle_enabled
            database.update_chat_setting(
                chat_id, "shuffle", int(state.shuffle_enabled)
            )

            if state.shuffle_enabled:
                database.shuffle_queue(chat_id)

            await send_or_update_panel(client, chat_id, state.player_message_id)
            return

        # ── Volume controls ────────────────────────────────────

        if action == "vol_up":
            await callback.answer()
            state.volume = min(200, state.volume + 10)
            database.update_chat_setting(chat_id, "default_volume", state.volume)
            await send_or_update_panel(client, chat_id, state.player_message_id)
            return

        if action == "vol_down":
            await callback.answer()
            state.volume = max(0, state.volume - 10)
            database.update_chat_setting(chat_id, "default_volume", state.volume)
            await send_or_update_panel(client, chat_id, state.player_message_id)
            return

        if action == "mute":
            await callback.answer()
            if state.volume > 0:
                state._prev_volume = state.volume
                state.volume = 0
            else:
                state.volume = getattr(state, "_prev_volume", 100)
            database.update_chat_setting(chat_id, "default_volume", state.volume)
            await send_or_update_panel(client, chat_id, state.player_message_id)
            return

        # ── Favorites ──────────────────────────────────────────

        if action == "save_fav":
            await callback.answer()
            if not state.now_playing:
                await callback.answer("Nothing playing to save", show_alert=True)
                return

            np = state.now_playing
            added = add_to_favorites(
                user_id,
                title=np.title,
                artist=np.artist,
                duration=np.duration,
                file_path=np.file_path,
                source=np.source,
            )

            if added:
                await callback.answer("❤️ Saved to favorites!", show_alert=True)
            else:
                await callback.answer("Already in your favorites", show_alert=True)
            return

        if action == "favs":
            await callback.answer()
            favs = database.get_favorites(user_id, limit=50)
            text = _build_favorites_text(favs, 0)
            keyboard = build_favorites_keyboard(user_id, 0)
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except Exception:
                pass
            return

        if action == "fpage":
            await callback.answer()
            page = int(arg) if arg.isdigit() else 0
            favs = database.get_favorites(user_id, limit=50)
            text = _build_favorites_text(favs, page)
            keyboard = build_favorites_keyboard(user_id, page)
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except Exception:
                pass
            return

        # ── Clear queue ────────────────────────────────────────

        if action == "clear_queue":
            await callback.answer()
            if not can_control_playback(user_id, chat_id):
                await callback.answer("⛔️ No permission", show_alert=True)
                return
            database.clear_queue(chat_id)
            await callback.answer("🧹 Queue cleared", show_alert=True)
            return

        # ── Refresh ────────────────────────────────────────────

        if action == "refresh":
            await callback.answer()
            await send_or_update_panel(client, chat_id, state.player_message_id)
            return

        # ── Close panel ────────────────────────────────────────

        if action == "close":
            await callback.answer()
            try:
                await callback.message.delete()
            except Exception:
                pass
            if state.player_message_id == callback.message.id:
                state.player_message_id = 0
            return

        # ── Search result selection ────────────────────────────

        if action == "sresult":
            await callback.answer()
            # arg = index into cached search results
            from handlers.search import get_cached_results
            results = get_cached_results(chat_id, user_id)
            if not results:
                await callback.answer("Search results expired. Search again.", show_alert=True)
                return

            try:
                idx = int(arg)
                if idx < 0 or idx >= len(results):
                    await callback.answer("Invalid selection", show_alert=True)
                    return
            except ValueError:
                await callback.answer("Invalid selection", show_alert=True)
                return

            selected = results[idx]
            song_id = selected.get("id", "")

            if not song_id:
                await callback.answer("Cannot play this result", show_alert=True)
                return

            await callback.answer("⏳ Downloading...")

            status = await client.send_message(
                chat_id,
                f"📥 Downloading: {escape_html(selected.get('title', 'Unknown'))}...",
            )

            try:
                from music.downloader import download_by_id
                result = await asyncio.to_thread(download_by_id, song_id)
            except Exception as e:
                logger.exception("Download failed for %s", song_id)
                try:
                    await status.edit_text(f"❌ Download failed: {e}")
                except Exception:
                    pass
                return

            if not result or not result.get("file_path"):
                try:
                    await status.edit_text("❌ Download failed — no result.")
                except Exception:
                    pass
                return

            from handlers.player import play_file
            await play_file(
                client,
                callback.message,
                calls,
                chat_id,
                file_path=result["file_path"],
                title=result.get("title", "Unknown"),
                artist=result.get("artist", ""),
                duration=result.get("duration", 0),
                requested_by=user_id,
                requested_by_name=get_user_name(callback.from_user),
                status_message=status,
                source="youtube",
            )
            return