import asyncio
import aiohttp
import os
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FASTAPI_URL = os.getenv("FASTAPI_URL")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот, который отправляет сообщения в FastAPI.")

@dp.message()
async def handle_message(message: Message):
    telegram_user_id = str(message.from_user.id)
    text = message.text
    sent_msg = await message.answer("🤖 Модель обрабатывает текст...")
    progress_message_id = sent_msg.message_id
    chat_id = message.chat.id
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{FASTAPI_URL}/messages", params={"telegram_user_id": telegram_user_id, "text": text, "progress_message_id": progress_message_id, "chat_id": chat_id}) as response:
            response_json = await response.json()
            # Если в ответе отсутствует поле "message", используем дефолтное сообщение
            message_text = response_json.get("message")
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_message_id,
                    text=message_text
                )
            except TelegramBadRequest as e:
                print(f"TelegramBadRequest при отправке ответа: {e}")
            except Exception as e:
                print(f"Ошибка при отправке ответа: {e}")

async def start_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start_bot())
