"""
Admin and start handlers.

/start — welcome message (private chat)
/admin — admin panel with stats, user list, group list, settings
on_added_to_group — welcome when bot joins a group
"""

import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import database
from services.permissions import (
    get_user_name,
    is_admin,
    is_owner,
    register_user_from_message,
)
from services import storage
from utils.helpers import escape_html

logger = logging.getLogger("hexiron.admin")


# ── /start ───────────────────────────────────────────────────────────


async def start(client: Client, message: Message):
    register_user_from_message(message)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Help", callback_data="adm:help"),
            InlineKeyboardButton("⚙️ Settings", callback_data="adm:settings"),
        ],
        [
            InlineKeyboardButton("📜 Queue", callback_data="pl:queue"),
            InlineKeyboardButton("❤️ Favorites", callback_data="pl:favs"),
        ],
    ])

    await message.reply_text(
        "🎵 <b>Welcome to HexIron Music Bot!</b>\n\n"
        "Add me to a group and make me admin with voice chat management permission, "
        "then use /play &lt;song name&gt; to start.\n\n"
        "<b>Commands:</b>\n"
        "/play &lt;name&gt; — Play or add to queue\n"
        "/pause — Pause playback\n"
        "/resume — Resume playback\n"
        "/skip — Skip current song\n"
        "/stop — Stop and clear queue\n"
        "/queue — View queue\n"
        "/panel — Open control panel\n"
        "/upload — Upload audio file\n"
        "/fav — View favorites\n"
        "/search &lt;query&gt; — Search for music",
        reply_markup=keyboard,
    )


# ── /help callback ───────────────────────────────────────────────────


def register_admin_handlers(bot: Client, calls):
    """Register all admin-related handlers."""

    @bot.on_callback_query(filters.regex(r"^adm:(.+)$"))
    async def handle_admin_callback(client: Client, callback: CallbackQuery):
        data = callback.data.split(":", 2)
        action = data[1] if len(data) > 1 else ""

        if action == "help":
            await callback.answer()
            try:
                await callback.message.edit_text(
                    "🎵 <b>HexIron Music Bot — Help</b>\n\n"
                    "<b>Player Commands:</b>\n"
                    "/play &lt;name&gt; — Play or queue a song\n"
                    "/pause — Pause playback\n"
                    "/resume — Resume playback\n"
                    "/skip — Skip to next song\n"
                    "/stop — Stop playback and clear queue\n"
                    "/queue — View the queue\n"
                    "/panel — Open the interactive control panel\n\n"
                    "<b>Upload:</b>\n"
                    "Send an audio file directly to play it\n\n"
                    "<b>Favorites:</b>\n"
                    "/fav — View your favorites\n"
                    "Use ❤️ button on now playing to save\n\n"
                    "<b>Search:</b>\n"
                    "/search &lt;query&gt; — Search for music",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data="adm:back"),
                    ]]),
                )
            except Exception:
                pass
            return

        if action == "back":
            await callback.answer()
            try:
                await callback.message.edit_text(
                    "🎵 <b>Welcome to HexIron Music Bot!</b>\n\n"
                    "Add me to a group and make me admin with voice chat management permission, "
                    "then use /play &lt;song name&gt; to start.",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("🎵 Help", callback_data="adm:help"),
                            InlineKeyboardButton("⚙️ Settings", callback_data="adm:settings"),
                        ],
                    ]),
                )
            except Exception:
                pass
            return

        if action == "settings":
            if not is_admin(callback.from_user.id):
                await callback.answer("⛔️ Admin only", show_alert=True)
                return
            await callback.answer()
            await _show_admin_panel(client, callback)
            return

        if action == "stats":
            if not is_admin(callback.from_user.id):
                await callback.answer("⛔️ Admin only", show_alert=True)
                return
            await callback.answer()
            await _show_stats(client, callback)
            return

        if action == "users":
            if not is_admin(callback.from_user.id):
                await callback.answer("⛔️ Admin only", show_alert=True)
                return
            await callback.answer()
            await _show_users(client, callback)
            return

        if action == "groups":
            if not is_admin(callback.from_user.id):
                await callback.answer("⛔️ Admin only", show_alert=True)
                return
            await callback.answer()
            await _show_groups(client, callback)
            return

        if action == "storage":
            if not is_admin(callback.from_user.id):
                await callback.answer("⛔️ Admin only", show_alert=True)
                return
            await callback.answer()
            await _show_storage(client, callback)
            return

        if action == "cleanup":
            if not is_admin(callback.from_user.id):
                await callback.answer("⛔️ Admin only", show_alert=True)
                return
            removed = storage.cleanup_temp_files()
            removed2 = storage.cleanup_stale_downloads()
            await callback.answer(
                f"Cleaned {removed + removed2} files", show_alert=True
            )
            return

        if action == "broadcast":
            if not is_owner(callback.from_user.id):
                await callback.answer("⛔️ Owner only", show_alert=True)
                return
            await callback.answer(
                "Send: /broadcast <message>",
                show_alert=True,
            )
            return

    # ── /admin command ───────────────────────────────────────────────

    @bot.on_message(filters.command("admin"))
    async def panel_cmd(client: Client, message: Message):
        register_user_from_message(message)

        if not is_admin(message.from_user.id):
            await message.reply_text("⛔️ This command is for admins only.")
            return

        await _show_admin_panel_message(client, message)

    # ── /panel command ───────────────────────────────────────────────

    @bot.on_message(filters.command("panel"))
    async def panel_open_cmd(client: Client, message: Message):
        register_user_from_message(message)

        chat_id = message.chat.id
        from handlers.control_panel import send_or_update_panel
        from services.player_state import get_state

        state = get_state(chat_id)
        panel_id = await send_or_update_panel(client, chat_id, state.player_message_id)
        state.player_message_id = panel_id

    # ── /fav command ─────────────────────────────────────────────────

    @bot.on_message(filters.command("fav"))
    async def fav_cmd(client: Client, message: Message):
        register_user_from_message(message)
        user_id = message.from_user.id

        from handlers.control_panel import build_favorites_keyboard, _build_favorites_text

        favs = database.get_favorites(user_id, limit=50)
        text = _build_favorites_text(favs, 0)
        keyboard = build_favorites_keyboard(user_id, 0)
        await message.reply_text(text, reply_markup=keyboard)

    # ── /search command ──────────────────────────────────────────────

    @bot.on_message(filters.command("search"))
    async def search_cmd(client: Client, message: Message):
        register_user_from_message(message)

        if len(message.command) < 2:
            await message.reply_text("Usage: /search <query>")
            return

        query = message.text.split(None, 1)[1].strip()
        if not query:
            await message.reply_text("Enter a search query.")
            return

        from music.downloader import search_results
        status = await message.reply_text(f"🔎 Searching: {query}")

        try:
            results = await asyncio.to_thread(search_results, query)
        except Exception as e:
            await status.edit_text(f"❌ Search error: {e}")
            return

        if not results:
            await status.edit_text("❌ No results found.")
            return

        # Build inline result buttons
        buttons = []
        for i, r in enumerate(results[:5]):
            title = r.get("title", "Unknown")
            buttons.append([
                InlineKeyboardButton(
                    f"▶️ {title[:30]}",
                    callback_data=f"pl:sresult:{i}",
                ),
            ])

        # Store results in a temporary way (we'll store in memory for now)
        from handlers.search import store_search_results
        search_id = store_search_results(message.chat.id, message.from_user.id, results)

        await status.edit_text(
            f"🔎 <b>Search results for:</b> {escape_html(query)}\n\n"
            + "\n".join(
                f"{i+1}. 🎵 {escape_html(r.get('title', 'Unknown'))}"
                for i, r in enumerate(results[:5])
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    # ── /broadcast command ───────────────────────────────────────────

    @bot.on_message(filters.command("broadcast"))
    async def broadcast_cmd(client: Client, message: Message):
        if not is_owner(message.from_user.id):
            await message.reply_text("⛔️ Owner only.")
            return

        if len(message.command) < 2:
            await message.reply_text("Usage: /broadcast <message>")
            return

        text = message.text.split(None, 1)[1].strip()
        groups = database.list_groups()
        sent = 0
        failed = 0

        status = await message.reply_text(
            f"📢 Broadcasting to {len(groups)} groups..."
        )

        for chat_id, title in groups:
            try:
                await client.send_message(chat_id, f"📢 <b>Announcement</b>\n\n{text}")
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.5)

        await status.edit_text(
            f"📢 Broadcast complete.\n"
            f"✅ Sent: {sent}\n"
            f"❌ Failed: {failed}"
        )


# ── Admin panel builders ─────────────────────────────────────────────


async def _show_admin_panel_message(client: Client, message: Message):
    """Show admin panel as a new message."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Statistics", callback_data="adm:stats"),
            InlineKeyboardButton("👥 Users", callback_data="adm:users"),
        ],
        [
            InlineKeyboardButton("💬 Groups", callback_data="adm:groups"),
            InlineKeyboardButton("📁 Storage", callback_data="adm:storage"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast"),
            InlineKeyboardButton("🧹 Cleanup", callback_data="adm:cleanup"),
        ],
    ])

    user_count = database.user_count()
    group_count = database.group_count()
    songs_played = database.get_stat("songs_played")

    await message.reply_text(
        f"🎛 <b>ADMIN PANEL</b>\n\n"
        f"👥 Users: {user_count}\n"
        f"💬 Groups: {group_count}\n"
        f"🎵 Songs played: {songs_played}",
        reply_markup=keyboard,
    )


async def _show_admin_panel(client: Client, callback: CallbackQuery):
    """Show admin panel via callback."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Statistics", callback_data="adm:stats"),
            InlineKeyboardButton("👥 Users", callback_data="adm:users"),
        ],
        [
            InlineKeyboardButton("💬 Groups", callback_data="adm:groups"),
            InlineKeyboardButton("📁 Storage", callback_data="adm:storage"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast"),
            InlineKeyboardButton("🧹 Cleanup", callback_data="adm:cleanup"),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="adm:back"),
        ],
    ])

    user_count = database.user_count()
    group_count = database.group_count()
    songs_played = database.get_stat("songs_played")

    text = (
        f"🎛 <b>ADMIN PANEL</b>\n\n"
        f"👥 Users: {user_count}\n"
        f"💬 Groups: {group_count}\n"
        f"🎵 Songs played: {songs_played}"
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass


async def _show_stats(client: Client, callback: CallbackQuery):
    """Show detailed statistics."""
    from services.player_state import active_chat_ids

    stats = database.get_all_stats()
    text = (
        f"📊 <b>STATISTICS</b>\n\n"
        f"👥 Total users: {database.user_count()}\n"
        f"💬 Active groups: {database.group_count()}\n"
        f"🎵 Songs played: {stats.get('songs_played', 0)}\n"
        f"📥 Total uploads: {stats.get('uploads', 0)}\n"
        f"🔍 Total searches: {stats.get('searches', 0)}\n"
        f"📡 Active streams: {len(active_chat_ids())}"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="adm:settings"),
            ]]),
        )
    except Exception:
        pass


async def _show_users(client: Client, callback: CallbackQuery):
    """Show recent users."""
    users = database.top_users(10)
    if not users:
        text = "👥 <b>USERS</b>\n\nNo users yet."
    else:
        lines = ["👥 <b>RECENT USERS</b>\n"]
        for u in users:
            name = escape_html(u.get("full_name", str(u["user_id"])))
            username = u.get("username", "")
            if username:
                lines.append(f"• {name} (@{username})")
            else:
                lines.append(f"• {name} (ID: {u['user_id']})")
        text = "\n".join(lines)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="adm:settings"),
            ]]),
        )
    except Exception:
        pass


async def _show_groups(client: Client, callback: CallbackQuery):
    """Show registered groups."""
    groups = database.list_groups()
    if not groups:
        text = "💬 <b>GROUPS</b>\n\nNo groups registered."
    else:
        lines = [f"💬 <b>GROUPS</b> ({len(groups)})\n"]
        for chat_id, title in groups[:20]:
            lines.append(f"• {escape_html(title)} ({chat_id})")
        if len(groups) > 20:
            lines.append(f"\n... and {len(groups) - 20} more")
        text = "\n".join(lines)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="adm:settings"),
            ]]),
        )
    except Exception:
        pass


async def _show_storage(client: Client, callback: CallbackQuery):
    """Show storage usage."""
    usage = storage.get_disk_usage()
    text = (
        f"📁 <b>STORAGE</b>\n\n"
        f"📥 Downloads: {usage.get('downloads', 'N/A')}\n"
        f"📤 Uploads: {usage.get('uploads', 'N/A')}\n"
        f"🗂 Temp: {usage.get('temp', 'N/A')}\n"
        f"💾 Cache: {usage.get('cache', 'N/A')}\n\n"
        f"💿 Disk Total: {usage.get('disk_total', 'N/A')}\n"
        f"💿 Disk Free: {usage.get('disk_free', 'N/A')}"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧹 Cleanup", callback_data="adm:cleanup")],
                [InlineKeyboardButton("🔙 Back", callback_data="adm:settings")],
            ]),
        )
    except Exception:
        pass


# ── Group join handler ───────────────────────────────────────────────


async def on_added_to_group(client: Client, message: Message):
    """Fires when the bot is added to a new group."""
    me = await client.get_me()
    added_ids = [u.id for u in (message.new_chat_members or [])]
    if me.id not in added_ids:
        return

    database.register_group(message.chat.id, message.chat.title or "")

    await asyncio.sleep(2)
    try:
        await client.send_message(
            message.chat.id,
            "✅ I've been added to this group!\n\n"
            "To play music, make me admin with voice chat management permission, "
            "then use /play &lt;song name&gt;.\n\n"
            "Use /panel for the interactive control panel.",
        )
    except Exception:
        pass
