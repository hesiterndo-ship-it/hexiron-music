"""
SQLite database layer for HexIron Music Bot.

Tables:
  - groups          : registered Telegram groups
  - users           : users who have interacted with the bot
  - queue           : per-chat playback queue
  - favorites       : per-user saved songs
  - chat_settings   : per-chat configuration
  - statistics      : aggregated stats counters
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from config import DATABASE_URL

_lock = threading.Lock()


@contextmanager
def get_conn():
    """Thread-safe short-lived SQLite connection."""
    conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create / migrate tables. Called once at startup."""
    db_dir = os.path.dirname(DATABASE_URL)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    with _lock, get_conn() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS groups (
                chat_id   INTEGER PRIMARY KEY,
                title     TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                added_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                full_name  TEXT,
                first_seen TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                title       TEXT NOT NULL DEFAULT '',
                artist      TEXT NOT NULL DEFAULT '',
                duration    INTEGER NOT NULL DEFAULT 0,
                file_path   TEXT NOT NULL DEFAULT '',
                source      TEXT NOT NULL DEFAULT 'search',
                requested_by INTEGER NOT NULL DEFAULT 0,
                added_at    TEXT NOT NULL DEFAULT (datetime('now')),
                sort_order  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS favorites (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                title    TEXT NOT NULL DEFAULT '',
                artist   TEXT NOT NULL DEFAULT '',
                duration INTEGER NOT NULL DEFAULT 0,
                file_path TEXT NOT NULL DEFAULT '',
                source   TEXT NOT NULL DEFAULT 'search',
                added_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, title, artist)
            );

            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id          INTEGER PRIMARY KEY,
                auto_play        INTEGER NOT NULL DEFAULT 1,
                default_volume   INTEGER NOT NULL DEFAULT 100,
                loop_mode        TEXT NOT NULL DEFAULT 'off',
                shuffle          INTEGER NOT NULL DEFAULT 0,
                max_queue_size   INTEGER NOT NULL DEFAULT 200,
                allow_uploads    INTEGER NOT NULL DEFAULT 1,
                allow_search     INTEGER NOT NULL DEFAULT 1,
                controls_allowed TEXT NOT NULL DEFAULT 'everyone',
                updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS statistics (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                metric TEXT NOT NULL,
                value  INTEGER NOT NULL DEFAULT 0,
                UNIQUE(metric)
            );
            """
        )

        # ------------------------------------------------------------
        # Database migrations
        # ------------------------------------------------------------

        queue_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(queue)").fetchall()
        }

        # Older databases may have a queue table without sort_order.
        if "sort_order" not in queue_columns:
            conn.execute(
                "ALTER TABLE queue "
                "ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
            )

        # Create the index only AFTER sort_order is guaranteed to exist.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_chat "
            "ON queue(chat_id, sort_order)"
        )

        conn.commit()


# ── groups ───────────────────────────────────────────────────────────


def register_group(chat_id: int, title: str):
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO groups(chat_id, title, is_active, added_at, updated_at) "
            "VALUES (?, ?, 1, datetime('now'), datetime('now'))",
            (chat_id, title),
        )
        conn.commit()


def remove_group(chat_id: int):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM groups WHERE chat_id=?", (chat_id,))
        conn.execute("DELETE FROM queue WHERE chat_id=?", (chat_id,))
        conn.execute("DELETE FROM chat_settings WHERE chat_id=?", (chat_id,))
        conn.commit()


def list_groups() -> List[Tuple]:
    with _lock, get_conn() as conn:
        return conn.execute(
            "SELECT chat_id, title FROM groups WHERE is_active=1 ORDER BY added_at"
        ).fetchall()


def group_count() -> int:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM groups WHERE is_active=1"
        ).fetchone()
        return row[0] if row else 0


# ── users ────────────────────────────────────────────────────────────


def register_user(user_id: int, username: str = "", full_name: str = ""):
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO users(user_id, username, full_name, first_seen, last_seen) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "username=excluded.username, full_name=excluded.full_name, "
            "last_seen=datetime('now')",
            (user_id, username, full_name),
        )
        conn.commit()


def get_user(user_id: int) -> Optional[Dict]:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def user_count() -> int:
    with _lock, get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return row[0] if row else 0


def top_users(limit: int = 10) -> List[Dict]:
    with _lock, get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── queue ────────────────────────────────────────────────────────────


def add_to_queue(
    chat_id: int,
    title: str,
    file_path: str,
    requested_by: int,
    artist: str = "",
    duration: int = 0,
    source: str = "search",
) -> int:
    """Add a track to the queue. Returns the queue item id."""
    with _lock, get_conn() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) "
            "FROM queue WHERE chat_id=?",
            (chat_id,),
        ).fetchone()[0]

        cur = conn.execute(
            "INSERT INTO queue("
            "chat_id, title, artist, duration, file_path, source, "
            "requested_by, added_at, sort_order"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)",
            (
                chat_id,
                title,
                artist,
                duration,
                file_path,
                source,
                requested_by,
                max_order + 1,
            ),
        )
        conn.commit()
        return cur.lastrowid


def pop_next(chat_id: int) -> Optional[Dict]:
    """Remove and return the next queued track, or None."""
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, artist, duration, file_path, source, requested_by "
            "FROM queue WHERE chat_id=? "
            "ORDER BY sort_order ASC LIMIT 1",
            (chat_id,),
        ).fetchone()

        if row is None:
            return None

        conn.execute("DELETE FROM queue WHERE id=?", (row["id"],))
        conn.commit()
        return dict(row)


def peek_queue(chat_id: int) -> List[Dict]:
    with _lock, get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, artist, duration, file_path, source, "
            "requested_by, added_at "
            "FROM queue WHERE chat_id=? ORDER BY sort_order ASC",
            (chat_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def queue_length(chat_id: int) -> int:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
        return row[0] if row else 0


def clear_queue(chat_id: int):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM queue WHERE chat_id=?", (chat_id,))
        conn.commit()


def remove_queue_item(chat_id: int, item_id: int) -> bool:
    with _lock, get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM queue WHERE id=? AND chat_id=?",
            (item_id, chat_id),
        )
        conn.commit()
        return cur.rowcount > 0


def shuffle_queue(chat_id: int):
    """Randomize sort_order for a chat's queue."""
    import random

    with _lock, get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM queue WHERE chat_id=? ORDER BY sort_order ASC",
            (chat_id,),
        ).fetchall()

        if len(rows) < 2:
            return

        ids = [r["id"] for r in rows]
        random.shuffle(ids)

        for idx, qid in enumerate(ids):
            conn.execute(
                "UPDATE queue SET sort_order=? WHERE id=?",
                (idx, qid),
            )

        conn.commit()


def move_queue_item(
    chat_id: int,
    item_id: int,
    new_position: int,
) -> bool:
    """Move a queue item to a new position."""
    with _lock, get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM queue WHERE chat_id=? ORDER BY sort_order ASC",
            (chat_id,),
        ).fetchall()

        ids = [r["id"] for r in rows]

        if item_id not in ids:
            return False

        new_pos = max(0, min(new_position, len(ids) - 1))

        ids.remove(item_id)
        ids.insert(new_pos, item_id)

        for idx, qid in enumerate(ids):
            conn.execute(
                "UPDATE queue SET sort_order=? WHERE id=?",
                (idx, qid),
            )

        conn.commit()
        return True


def remove_stale_queue_items(max_age_hours: int = 24):
    """Remove queue items older than max_age_hours."""
    with _lock, get_conn() as conn:
        conn.execute(
            "DELETE FROM queue WHERE added_at < datetime('now', ?)",
            (f"-{max_age_hours} hours",),
        )
        conn.commit()


# ── favorites ────────────────────────────────────────────────────────


def add_favorite(
    user_id: int,
    title: str,
    artist: str = "",
    duration: int = 0,
    file_path: str = "",
    source: str = "search",
) -> bool:
    with _lock, get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO favorites("
                "user_id, title, artist, duration, file_path, source, added_at"
                ") VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                (
                    user_id,
                    title,
                    artist,
                    duration,
                    file_path,
                    source,
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def remove_favorite(
    user_id: int,
    title: str,
    artist: str = "",
) -> bool:
    with _lock, get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM favorites "
            "WHERE user_id=? AND title=? AND artist=?",
            (user_id, title, artist),
        )
        conn.commit()
        return cur.rowcount > 0


def get_favorites(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict]:
    with _lock, get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM favorites "
            "WHERE user_id=? ORDER BY added_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def favorite_count(user_id: int) -> int:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM favorites WHERE user_id=?",
            (user_id,),
        ).fetchone()
        return row[0] if row else 0


def is_favorite(
    user_id: int,
    title: str,
    artist: str = "",
) -> bool:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM favorites "
            "WHERE user_id=? AND title=? AND artist=?",
            (user_id, title, artist),
        ).fetchone()
        return row is not None


# ── chat settings ────────────────────────────────────────────────────


_DEFAULT_SETTINGS: Dict[str, Any] = {
    "auto_play": 1,
    "default_volume": 100,
    "loop_mode": "off",
    "shuffle": 0,
    "max_queue_size": 200,
    "allow_uploads": 1,
    "allow_search": 1,
    "controls_allowed": "everyone",
}


def get_chat_settings(chat_id: int) -> Dict:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM chat_settings WHERE chat_id=?",
            (chat_id,),
        ).fetchone()

        if row:
            return dict(row)

        conn.execute(
            "INSERT INTO chat_settings(chat_id) VALUES (?)",
            (chat_id,),
        )
        conn.commit()

        return dict(_DEFAULT_SETTINGS, chat_id=chat_id)


def update_chat_setting(
    chat_id: int,
    key: str,
    value,
):
    allowed = set(_DEFAULT_SETTINGS.keys())

    if key not in allowed:
        return False

    with _lock, get_conn() as conn:
        conn.execute(
            f"UPDATE chat_settings SET {key}=?, "
            "updated_at=datetime('now') WHERE chat_id=?",
            (value, chat_id),
        )

        conn.execute(
            "INSERT OR IGNORE INTO chat_settings(chat_id) VALUES (?)",
            (chat_id,),
        )

        conn.commit()
        return True


# ── statistics ───────────────────────────────────────────────────────


def incr_stat(metric: str, amount: int = 1):
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO statistics(metric, value) VALUES (?, ?) "
            "ON CONFLICT(metric) DO UPDATE SET value=value+?",
            (metric, amount, amount),
        )
        conn.commit()


def get_stat(metric: str) -> int:
    with _lock, get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM statistics WHERE metric=?",
            (metric,),
        ).fetchone()
        return row[0] if row else 0


def get_all_stats() -> Dict[str, int]:
    with _lock, get_conn() as conn:
        rows = conn.execute(
            "SELECT metric, value FROM statistics"
        ).fetchall()
        return {r["metric"]: r["value"] for r in rows}


def set_stat(metric: str, value: int):
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO statistics(metric, value) VALUES (?, ?) "
            "ON CONFLICT(metric) DO UPDATE SET value=?",
            (metric, value, value),
        )
        conn.commit()
