import aiosqlite
import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/messages.db")

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
                processed INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        await db.commit()



async def insert_message(user_id: str, text: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Вставляем сообщение
        cursor = await db.execute(
            "INSERT INTO messages (user_id, text) VALUES (?, ?)",
            (user_id, text)
        )
        await db.commit()

        # Получаем ID последнего вставленного сообщения
        last_row_id = cursor.lastrowid

        return last_row_id


async def fetch_unread_messages(telegram_user_id: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Находим user_id по telegram_user_id
        # Выбираем все сообщения, где processed = 0
        async with db.execute("""
            SELECT id, text, created_at 
            FROM messages 
            WHERE user_id = ? AND processed = 0
            ORDER BY id ASC
        """, (telegram_user_id,)) as cursor:  # Обратите внимание на кортеж (user_id,)
            messages = await cursor.fetchall()

        return [
            {"id": m[0], "text": m[1], "created_at": m[2]}
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
