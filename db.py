import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "chat.db"  # файл бази лежить поруч з кодом
NEW_CHAT_TITLE = "Новий чат"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # рядки можна читати як словник: row["role"]
    # у SQLite зв'язки між таблицями (FOREIGN KEY) вимкнені за замовчуванням —
    # без цього рядка ON DELETE CASCADE просто не спрацює
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Створює таблиці, якщо їх ще немає. Викликається при старті сервера."""
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        migrate_old_messages(conn)
        # індекс, щоб швидко знаходити повідомлення одного чату (як у завданні 24)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS messages_chat_id_idx ON messages (chat_id)"
        )


def migrate_old_messages(conn):
    """Стара база (до панелі чатів) не мала chat_id. Додаємо колонку
    і переносимо всю стару історію в «Перший чат»."""
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(messages)")]
    if "chat_id" in columns:
        return  # база вже нового формату

    conn.execute(
        "ALTER TABLE messages ADD COLUMN chat_id INTEGER "
        "REFERENCES chats(id) ON DELETE CASCADE"
    )
    if conn.execute("SELECT 1 FROM messages LIMIT 1").fetchone():
        chat_id = conn.execute(
            "INSERT INTO chats (title) VALUES ('Перший чат')"
        ).lastrowid
        conn.execute("UPDATE messages SET chat_id = ?", (chat_id,))


def list_chats():
    """Усі чати, найновіші зверху."""
    with connect() as conn:
        rows = conn.execute("SELECT id, title FROM chats ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def create_chat():
    with connect() as conn:
        chat_id = conn.execute(
            "INSERT INTO chats (title) VALUES (?)", (NEW_CHAT_TITLE,)
        ).lastrowid
    return {"id": chat_id, "title": NEW_CHAT_TITLE}


def get_chat(chat_id):
    """Чат за id, або None, якщо такого немає."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
    return dict(row) if row else None


def rename_chat(chat_id, title):
    with connect() as conn:
        conn.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))


def delete_chat(chat_id):
    """Повертає True, якщо чат існував. Повідомлення видаляються каскадно."""
    with connect() as conn:
        cursor = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    return cursor.rowcount > 0


def add_message(chat_id, role, content):
    """Повертає збережене повідомлення разом з id — він потрібен фронту для кнопок."""
    with connect() as conn:
        message_id = conn.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        ).lastrowid
    return {"id": message_id, "role": role, "content": content}


def get_messages(chat_id):
    """Історія одного чату від найстарішого повідомлення до найновішого."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, role, content FROM messages WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_message(message_id):
    """Повертає True, якщо повідомлення існувало."""
    with connect() as conn:
        cursor = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    return cursor.rowcount > 0
