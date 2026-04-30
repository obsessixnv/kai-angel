import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = os.getenv("DB_PATH", "bot_data.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            message_text TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            is_bot INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
        CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            activity_mode TEXT NOT NULL DEFAULT 'small',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def save_message(chat_id: int, user_id: int, username: Optional[str],
                 message_text: str, timestamp: datetime, is_bot: bool = False):
    conn = get_db()
    conn.execute(
        """INSERT INTO messages (chat_id, user_id, username, message_text, timestamp, is_bot)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (chat_id, user_id, username, message_text, timestamp.isoformat(), int(is_bot))
    )
    conn.commit()
    conn.close()


def get_chat_history(chat_id: int, limit: int = 500) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.execute(
        """SELECT username, message_text, timestamp, is_bot
           FROM messages
           WHERE chat_id = ?
           ORDER BY timestamp DESC
           LIMIT ?""",
        (chat_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in reversed(rows)]


def get_chat_mode(chat_id: int) -> str:
    conn = get_db()
    cursor = conn.execute(
        "SELECT activity_mode FROM chat_settings WHERE chat_id = ?",
        (chat_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row["activity_mode"] if row else "small"


def set_chat_mode(chat_id: int, mode: str):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO chat_settings (chat_id, activity_mode, created_at, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET
               activity_mode = excluded.activity_mode,
               updated_at = excluded.updated_at""",
        (chat_id, mode.lower(), now, now)
    )
    conn.commit()
    conn.close()
