import sqlite3
import os

DB_PATH = "participants.db"


def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                data TEXT,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE UNIQUE INDEX idx_user_platform ON participants (user_id, platform);")
        conn.commit()
        conn.close()


def save_participant(user_id: int, platform: str, data: str):
    # 🔴 ИСПРАВЛЕНО: ДОБАВИЛ data: str И ПРОВЕРКУ
    if not user_id or not platform or not data:
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO participants (user_id, platform, data)
        VALUES (?, ?, ?)
    """, (user_id, platform, data))
    conn.commit()
    conn.close()


def get_all_participants():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, platform, data, completed_at FROM participants ORDER BY completed_at DESC")
    results = cursor.fetchall()
    conn.close()
    return results