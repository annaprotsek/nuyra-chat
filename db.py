import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "chat.db"  # файл бази лежить поруч з кодом


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # рядки можна читати як словник: row["role"]
    return conn


def init_db():
    """Створює таблицю, якщо її ще немає. Викликається при старті сервера."""
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def add_message(role, content):
    with connect() as conn:
        conn.execute(
            "INSERT INTO messages (role, content) VALUES (?, ?)",
            (role, content),
        )


def get_messages():
    """Уся історія від найстарішого повідомлення до найновішого."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id"
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]
