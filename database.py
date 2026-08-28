import sqlite3
from contextlib import contextmanager

DB_PATH = "hexiron.db"


@contextmanager
def get_conn():
    """Open a short-lived connection per use instead of one global
    connection at import time (safer under an asyncio event loop and
    avoids 'database is locked' errors when multiple handlers run)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist. Call this once at startup."""
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS groups("
            "chat_id INTEGER PRIMARY KEY, title TEXT, added_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS queue("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, "
            "title TEXT, file_path TEXT, requested_by INTEGER, added_at TEXT)"
        )
        conn.commit()


# ---------- groups ----------

def register_group(chat_id: int, title: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO groups(chat_id, title, added_at) "
            "VALUES (?, ?, datetime('now'))",
            (chat_id, title),
        )
        conn.commit()


def remove_group(chat_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM groups WHERE chat_id=?", (chat_id,))
        conn.commit()


def list_groups():
    with get_conn() as conn:
        return conn.execute("SELECT chat_id, title FROM groups").fetchall()


def group_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]


# ---------- queue ----------

def add_to_queue(chat_id: int, title: str, file_path: str, requested_by: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO queue(chat_id, title, file_path, requested_by, added_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (chat_id, title, file_path, requested_by),
        )
        conn.commit()


def pop_next(chat_id: int):
    """Remove and return the oldest queued track for this chat, or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, file_path FROM queue WHERE chat_id=? "
            "ORDER BY id ASC LIMIT 1",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM queue WHERE id=?", (row[0],))
        conn.commit()
        return {"title": row[1], "file_path": row[2]}


def peek_queue(chat_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT title FROM queue WHERE chat_id=? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
        return [r[0] for r in rows]


def clear_queue(chat_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM queue WHERE chat_id=?", (chat_id,))
        conn.commit()
