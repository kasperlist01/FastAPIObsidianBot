import asyncio

import aiohttp
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://api:8000")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот, который отправляет сообщения в FastAPI.")

@dp.message()
async def handle_message(message: Message):
    telegram_user_id = str(message.from_user.id)
    text = message.text

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{FASTAPI_URL}/messages", params={"telegram_user_id": telegram_user_id, "text": text}) as response:
            if response.status == 200:
                await message.reply("✅ Сообщение отправлено в FastAPI и WebSocket.")
            else:
                await message.reply("❌ Ошибка при отправке в FastAPI.")

async def start_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start_bot())
