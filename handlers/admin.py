import asyncio

from pyrogram import Client
from pyrogram.types import Message

import database
from utils.helpers import is_owner


async def start(client: Client, message: Message):
    await message.reply_text(
        "🎵 سلام! من ربات موزیک هستم.\n\n"
        "منو به یک گروه اضافه کن و ادمینم کن (دسترسی مدیریت ویس‌چت لازمه)، "
        "بعد با دستور /play <اسم آهنگ> پخش رو شروع کن.\n\n"
        "دستورات:\n"
        "/play <اسم آهنگ> — پخش یا افزودن به صف\n"
        "/pause — توقف موقت\n"
        "/resume — ادامه پخش\n"
        "/skip — رد کردن آهنگ فعلی\n"
        "/stop — توقف کامل و خروج از ویس‌چت\n"
        "/queue — نمایش صف پخش"
    )


async def panel(client: Client, message: Message):
    """Owner-only admin panel with basic stats."""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔️ این دستور فقط برای مالک ربات است.")
        return

    count = database.group_count()
    await message.reply_text(
        f"🎛 پنل ادمین\n\nتعداد گروه‌های متصل: {count}"
    )


async def on_added_to_group(client: Client, message: Message):
    """Fires when the bot is added to a new group (new_chat_members includes
    the bot itself). Registers the group and sends a welcome message.

    A short delay is required: right after the join update arrives,
    Telegram's MTProto layer may not have cached the channel/supergroup
    access hash yet, which makes an immediate reply raise CHANNEL_PRIVATE.
    """
    me = await client.get_me()
    added_ids = [u.id for u in (message.new_chat_members or [])]
    if me.id not in added_ids:
        return

    database.register_group(message.chat.id, message.chat.title or "")

    await asyncio.sleep(2)
    try:
        await client.send_message(
            message.chat.id,
            "✅ به این گروه اضافه شدم!\n"
            "برای اینکه بتونم آهنگ پخش کنم لطفاً منو ادمین کن و دسترسی "
            "«مدیریت ویس‌چت» رو فعال کن.\n\n"
            "بعد با /play <اسم آهنگ> شروع کن.",
        )
    except Exception:
        # Non-fatal: welcome message is a nice-to-have, not required for
        # the bot to function. If it still fails, just skip it silently.
        pass
