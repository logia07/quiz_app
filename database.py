import sqlite3
import os

DB_PATH = "participants.db"


def init_db():
    """Инициализация базы данных — с колонкой для результата."""
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                result_url TEXT,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()


def save_participant(user_id: str, platform: str,  str = None, result_url: str = None):
    """
    Сохранение факта заполнения анкеты + ссылка на результат.
    🔴 ПРОВЕРКА НА ДУБЛИКАТЫ — ЕСЛИ ПОЛЬЗОВАТЕЛЬ ЕСТЬ, ОБНОВЛЯЕМ

    Args:
        user_id: ID пользователя (строка, т.к. может быть "anonymous")
        platform: Платформа (vk, telegram, web)
        data: Не используется (оставлен для совместимости с main.py)
        result_url: Ссылка на результат (например: "/r/abc12345")
    """
    if not user_id or not platform:
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 🔴 ПРОВЕРКА — ЕСЛИ ПОЛЬЗОВАТЕЛЬ УЖЕ ЕСТЬ
    cursor.execute(
        "SELECT id FROM participants WHERE user_id = ? AND platform = ?",
        (user_id, platform)
    )
    existing = cursor.fetchone()

    if existing:
        # 🔴 ПОЛЬЗОВАТЕЛЬ ЕСТЬ — ОБНОВЛЯЕМ result_url и дату
        cursor.execute(
            """UPDATE participants 
               SET result_url = ?, completed_at = CURRENT_TIMESTAMP 
               WHERE user_id = ? AND platform = ?""",
            (result_url, user_id, platform)
        )
    else:
        # 🔴 НОВЫЙ ПОЛЬЗОВАТЕЛЬ — ДОБАВЛЯЕМ
        cursor.execute("""
            INSERT INTO participants (user_id, platform, result_url)
            VALUES (?, ?, ?)
        """, (user_id, platform, result_url))

    conn.commit()
    conn.close()


def get_all_participants():
    """Получение всех участников + ссылки на результаты."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, platform, result_url, completed_at 
        FROM participants 
        ORDER BY completed_at DESC
    """)
    results = cursor.fetchall()
    conn.close()
    return results