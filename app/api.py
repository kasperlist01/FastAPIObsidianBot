import asyncio
import logging
import time

import requests
import os
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from dotenv import load_dotenv
from openai_client import generate_response, generate_claude_response
from database import fetch_unread_messages, insert_message, mark_message_as_processed

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# === Настройка логирования ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()

# Разрешаем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Храним активные WebSocket-соединения и их состояние
active_connections: Dict[str, WebSocket] = {}
pending_acks: Dict[str, Dict] = {}  # Ожидаемые подтверждения сообщений

PING_INTERVAL = 30  # Каждые 30 секунд отправляем ping
PING_TIMEOUT = 10   # Ожидаем pong максимум 10 секунд
ACK_TIMEOUT = 5     # Ожидаем подтверждение сообщений 5 секунд

@app.post("/messages")
async def add_message(telegram_user_id: str, text: str, progress_message_id: int, chat_id: int):
    """Добавляет сообщение в БД и отправляет клиенту по WebSocket"""
    model_text = await generate_claude_response(text)
    db_message_id = await insert_message(telegram_user_id, text, model_text, chat_id, progress_message_id)
    print({"progress_message_id": progress_message_id, "chat_id": chat_id})

    logger.info(f"Новое сообщение {db_message_id} от {telegram_user_id}: {text}")

    # Если пользователь в сети, отправляем сообщение
    if telegram_user_id in active_connections:
        websocket = active_connections[telegram_user_id]
        data_to_send = {
            "db_message_id": db_message_id,
            "type": "new_message",
            "text": text,
            "model_text": model_text,
            "chat_id": chat_id,
            "progress_message_id": progress_message_id
        }
        await send_with_ack(websocket, telegram_user_id, data_to_send)

    return {"status": "ok", "message": "✅ Сообщение отредактировано моделью!"}

@app.websocket("/ws/{telegram_user_id}")
async def websocket_endpoint(websocket: WebSocket, telegram_user_id: str):
    """Основной обработчик WebSocket-соединения"""
    await websocket.accept()
    active_connections[telegram_user_id] = websocket
    logger.info(f"📡 WebSocket подключен: {telegram_user_id}")

    # Создаём событие для ожидания pong
    pong_event = asyncio.Event()

    # Запуск фоновой задачи пинга, передавая pong_event
    asyncio.create_task(ping_loop(websocket, telegram_user_id, pong_event))

    # Отправляем все непрочитанные сообщения
    messages = await fetch_unread_messages(telegram_user_id)
    for message in messages:
        time.sleep(0.1)
        data_to_send = {
            "type": "new_message",
            "db_message_id": message["id"],
            "text": message["text"],
            "created_at": message["created_at"],
            "chat_id": message["chat_id"],
            "progress_message_id": message["progress_message_id"],
            "model_text": message["model_text"],
        }
        await send_with_ack(websocket, telegram_user_id, data_to_send)

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except RuntimeError as e:
                logger.error(f"RuntimeError при получении сообщения: {e}")
                break

            # Если получен pong, сигнализируем фоновой задаче
            if data.get("type") == "pong":
                logger.info(f"✅ Получен pong от {telegram_user_id}")
                pong_event.set()
                continue

            # Обработка подтверждения доставки сообщений (ACK)
            if data.get("type") == "confirm":
                db_message_id = data.get("db_message_id")
                progress_message_id = data.get("progress_message_id")
                chat_id = data.get("chat_id")
                if db_message_id in pending_acks.get(telegram_user_id, {}):
                    del pending_acks[telegram_user_id][db_message_id]
                    await mark_message_as_processed(db_message_id)
                    edit_telegram_message(chat_id, progress_message_id, '🚀 Сообщение успешно отправлено!')
                    logger.info(f"✅ Сообщение {db_message_id} подтверждено {telegram_user_id} progress_message_id - {progress_message_id} chat_id - {chat_id}")
                continue

            logger.warning(f"⚠️ Неизвестный тип сообщения от {telegram_user_id}: {data}")

    except WebSocketDisconnect:
        logger.warning(f"❌ WebSocket отключен: {telegram_user_id}")
    finally:
        if telegram_user_id in active_connections:
            del active_connections[telegram_user_id]

async def ping_loop(websocket: WebSocket, telegram_user_id: str, pong_event: asyncio.Event):
    """Фоновая задача для отправки ping и ожидания pong через событие"""
    while telegram_user_id in active_connections:
        await asyncio.sleep(PING_INTERVAL)
        try:
            pong_event.clear()
            await websocket.send_json({"type": "ping"})
            logger.info(f"📤 Ping -> {telegram_user_id}")
            # Ждём, пока pong_event не будет установлен, или истечёт таймаут
            await asyncio.wait_for(pong_event.wait(), timeout=PING_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Pong не получен от {telegram_user_id} в течение {PING_TIMEOUT} секунд, закрываю соединение")
            await websocket.close()
            if telegram_user_id in active_connections:
                del active_connections[telegram_user_id]
            break
        except Exception as e:
            logger.error(f"Ошибка при отправке ping: {e}")
            break

async def send_with_ack(websocket: WebSocket, telegram_user_id: str, message: dict):
    """Отправка сообщения с ожиданием подтверждения (ACK)"""
    db_message_id = message["db_message_id"]

    if telegram_user_id not in pending_acks:
        pending_acks[telegram_user_id] = {}

    pending_acks[telegram_user_id][db_message_id] = message

    await websocket.send_json(message)
    logger.info(f"📤 Отправлено сообщение {db_message_id} -> {telegram_user_id}, ждем ACK")

    asyncio.create_task(check_ack_timeout(websocket, telegram_user_id, db_message_id))

async def check_ack_timeout(websocket: WebSocket, telegram_user_id: str, db_message_id: int):
    """Проверяем, пришел ли ACK на сообщение"""
    await asyncio.sleep(ACK_TIMEOUT)
    if telegram_user_id in pending_acks and db_message_id in pending_acks[telegram_user_id]:
        logger.error(f"❌ ACK не получен для сообщения {db_message_id} от {telegram_user_id}")
        del pending_acks[telegram_user_id][db_message_id]


def edit_telegram_message(chat_id: int, message_id: int, new_text: str):
    """
    Изменяет текст существующего сообщения в Telegram по его chat_id и message_id.

    :param chat_id: ID чата, в котором находится сообщение
    :param message_id: ID сообщения, которое нужно изменить
    :param new_text: Новый текст сообщения
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": new_text
    }

    try:
        response = requests.post(url, data=data, timeout=5)
        response.raise_for_status()
        result = response.json()

        if result.get("ok"):
            return True
        else:
            logger.error(f"❌ Ошибка при обновлении сообщения {message_id}: {result}")
            return False

    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе к Telegram API: {e}")
        return False

def start_api():
    """Запуск FastAPI-сервера"""
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start_api()
