import aiosqlite
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = "../data/messages.db"

async def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)  # Создаем папку, если нет
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id TEXT NOT NULL UNIQUE,
                username TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                progress_message_id INTEGER NOT NULL,
                model_text TEXT NOT NULL,
                plan_date TEXT NOT NULL,
                processed INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        await db.commit()

async def insert_message(user_id: str, text: str, model_text: str, chat_id: int, progress_message_id: int, plan_date: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO messages (user_id, text, model_text, chat_id, progress_message_id, plan_date) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, text, model_text, chat_id, progress_message_id, plan_date)
        )
        await db.commit()
        last_row_id = cursor.lastrowid
        return last_row_id


async def fetch_unread_messages(telegram_user_id: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Находим user_id по telegram_user_id
        # Выбираем все сообщения, где processed = 0
        async with db.execute("""
            SELECT id, text, created_at, chat_id, progress_message_id, model_text
            FROM messages 
            WHERE user_id = ? AND processed = 0
            ORDER BY id ASC
        """, (telegram_user_id,)) as cursor:  # Обратите внимание на кортеж (user_id,)
            messages = await cursor.fetchall()

        return [
            {"id": m[0], "text": m[1], "created_at": m[2], "chat_id": m[3], "progress_message_id": m[4], "model_text": m[5]}
            for m in messages
        ]


async def mark_message_as_processed(message_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT id FROM messages WHERE id = ? AND processed = 0", (message_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False  # Сообщение не найдено или уже обработано
        await db.execute("UPDATE messages SET processed = 1 WHERE id = ?", (message_id,))
        await db.commit()
        return True
