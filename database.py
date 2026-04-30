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
            chat_type TEXT,
            last_proactive_at TEXT,
            next_proactive_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            display_name TEXT,
            vibe_score REAL DEFAULT 0,
            relationship TEXT DEFAULT 'знакомый',
            notes TEXT DEFAULT '',
            interaction_count INTEGER DEFAULT 0,
            last_analyzed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(chat_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_profiles_chat_user ON user_profiles(chat_id, user_id);

        CREATE TABLE IF NOT EXISTS user_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            memory_text TEXT NOT NULL,
            importance INTEGER DEFAULT 3,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_chat_user ON user_memories(chat_id, user_id);
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


def set_chat_mode(chat_id: int, mode: str, chat_type: str = None):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO chat_settings (chat_id, activity_mode, chat_type, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET
               activity_mode = excluded.activity_mode,
               chat_type = COALESCE(excluded.chat_type, chat_settings.chat_type),
               updated_at = excluded.updated_at""",
        (chat_id, mode.lower(), chat_type, now, now)
    )
    conn.commit()
    conn.close()


def get_chats_due_for_proactive(current_time: datetime) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.execute(
        """SELECT chat_id, activity_mode, last_proactive_at, next_proactive_at
           FROM chat_settings
           WHERE (next_proactive_at IS NULL OR next_proactive_at <= ?)
             AND activity_mode != 'off'""",
        (current_time.isoformat(),)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def schedule_next_proactive(chat_id: int, current_time: datetime, hours: float):
    from datetime import timedelta
    next_time = current_time + timedelta(hours=hours)
    conn = get_db()
    conn.execute(
        """UPDATE chat_settings
           SET last_proactive_at = ?, next_proactive_at = ?
           WHERE chat_id = ?""",
        (current_time.isoformat(), next_time.isoformat(), chat_id)
    )
    conn.commit()
    conn.close()


# ─── User Profiles ───

def get_or_create_user_profile(chat_id: int, user_id: int, username: Optional[str],
                               display_name: Optional[str]) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM user_profiles WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )
    row = cursor.fetchone()
    if row:
        conn.close()
        return dict(row)

    now = datetime.utcnow().isoformat()
    conn.execute(
        """INSERT INTO user_profiles
           (chat_id, user_id, username, display_name, vibe_score, relationship, notes,
            interaction_count, last_analyzed_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, 0, 'знакомый', '', 0, ?, ?, ?)""",
        (chat_id, user_id, username, display_name, now, now, now)
    )
    conn.commit()
    cursor = conn.execute(
        "SELECT * FROM user_profiles WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row)


def increment_interaction_count(chat_id: int, user_id: int):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        """UPDATE user_profiles
           SET interaction_count = interaction_count + 1, updated_at = ?
           WHERE chat_id = ? AND user_id = ?""",
        (now, chat_id, user_id)
    )
    conn.commit()
    conn.close()


def update_user_profile(chat_id: int, user_id: int, vibe_score: float,
                        relationship: str, notes: str):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        """UPDATE user_profiles
           SET vibe_score = ?, relationship = ?, notes = ?, last_analyzed_at = ?, updated_at = ?
           WHERE chat_id = ? AND user_id = ?""",
        (vibe_score, relationship, notes, now, now, chat_id, user_id)
    )
    conn.commit()
    conn.close()


# ─── User Memories ───

def add_user_memory(chat_id: int, user_id: int, memory_text: str, importance: int = 3):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO user_memories (chat_id, user_id, memory_text, importance, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (chat_id, user_id, memory_text, importance, now)
    )
    conn.commit()
    conn.close()


def get_user_memories(chat_id: int, user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.execute(
        """SELECT memory_text, importance, created_at
           FROM user_memories
           WHERE chat_id = ? AND user_id = ?
           ORDER BY importance DESC, created_at DESC
           LIMIT ?""",
        (chat_id, user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_recent_messages(chat_id: int, user_id: int, limit: int = 15) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.execute(
        """SELECT message_text, timestamp
           FROM messages
           WHERE chat_id = ? AND user_id = ? AND is_bot = 0
           ORDER BY timestamp DESC
           LIMIT ?""",
        (chat_id, user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in reversed(rows)]


def get_recent_speaker_ids(chat_id: int, limit_messages: int = 20) -> List[int]:
    conn = get_db()
    cursor = conn.execute(
        """SELECT DISTINCT user_id
           FROM messages
           WHERE chat_id = ? AND is_bot = 0 AND user_id != 0
           ORDER BY timestamp DESC
           LIMIT ?""",
        (chat_id, limit_messages)
    )
    rows = cursor.fetchall()
    conn.close()
    return [row["user_id"] for row in rows]


def get_recent_speaker_profiles(chat_id: int, user_ids: List[int]) -> List[Dict[str, Any]]:
    if not user_ids:
        return []
    conn = get_db()
    placeholders = ",".join("?" * len(user_ids))
    cursor = conn.execute(
        f"""SELECT user_id, username, display_name, vibe_score, relationship, notes
            FROM user_profiles
            WHERE chat_id = ? AND user_id IN ({placeholders})""",
        (chat_id, *user_ids)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
