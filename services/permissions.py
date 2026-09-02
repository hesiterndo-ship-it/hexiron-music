"""
User permission checks and registration.

Centralises:
  - Owner / admin detection
  - Per-chat permission checks (upload, control, search)
  - User registration from Telegram messages
"""

import logging

from config import OWNER_ID, ADMIN_IDS
import database

logger = logging.getLogger("hexiron.permissions")


# ── Identity checks ────────────────────────────────────────────────


def is_owner(user_id: int) -> bool:
    """Check if user_id is the bot owner."""
    return user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    """Check if user_id is an admin or the owner."""
    if user_id == OWNER_ID:
        return True
    return user_id in ADMIN_IDS


# ── Per-chat permission checks ─────────────────────────────────────


def can_upload(user_id: int, chat_id: int) -> bool:
    """Check if user is allowed to upload music in this chat."""
    if is_admin(user_id):
        return True
    settings = database.get_chat_settings(chat_id)
    return bool(settings.get("allow_uploads", 1))


def can_control_playback(user_id: int, chat_id: int) -> bool:
    """Check if user is allowed to control playback in this chat."""
    if is_admin(user_id):
        return True
    settings = database.get_chat_settings(chat_id)
    controls = settings.get("controls_allowed", "everyone")
    if controls == "everyone":
        return True
    if controls == "admins":
        return is_admin(user_id)
    return False


def can_search(user_id: int, chat_id: int) -> bool:
    """Check if user is allowed to search in this chat."""
    if is_admin(user_id):
        return True
    settings = database.get_chat_settings(chat_id)
    return bool(settings.get("allow_search", 1))


# ── User helpers ────────────────────────────────────────────────────


def get_user_name(user) -> str:
    """Extract a display name from a Pyrogram User object."""
    if user is None:
        return "Unknown"
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return str(user.id)


def register_user_from_message(message) -> None:
    """Register/update a user from a Pyrogram Message."""
    user = message.from_user
    if user is None:
        return
    try:
        database.register_user(
            user_id=user.id,
            username=user.username or "",
            full_name=get_user_name(user),
        )
    except Exception:
        logger.debug("Failed to register user %s", user.id)
