import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

from database import fetch_unread_messages, insert_message, mark_message_as_processed
from typing import Dict

load_dotenv()

app = FastAPI()

# Разрешаем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Активные WebSocket-соединения
active_connections: Dict[str, WebSocket] = {}


@app.post("/messages")
async def add_message(telegram_user_id: str, text: str):
    """Добавляет сообщение в БД и уведомляет WebSocket-клиентов."""
    # Добавляем сообщение в БД
    message_id = await insert_message(telegram_user_id, text)
    print(message_id)

    # Если у пользователя есть активное WebSocket-соединение — отправляем сообщение
    if telegram_user_id in active_connections:
        websocket = active_connections[telegram_user_id]
        data_to_send = {
            "message_id": message_id,
            "type": "new_message",
            "text": text
        }
        print("Отправлено сообщение", data_to_send)
        await websocket.send_json(data_to_send)

        # Ожидаем подтверждения от клиента
        confirmation = await websocket.receive_json()
        if confirmation.get("type") == "confirm" and confirmation.get("message_id") == message_id:
            success = await mark_message_as_processed(message_id)
            if success:
                print(f"Сообщение {message_id} подтверждено и отмечено как обработанное")
            else:
                print(f"Не удалось подтвердить сообщение {message_id}")
        else:
            print("Получено неожиданное сообщение", confirmation)

    return {"status": "ok", "message": "Message added and sent via WebSocket"}


@app.websocket("/ws/{telegram_user_id}")
async def websocket_endpoint(websocket: WebSocket, telegram_user_id: str):
    await websocket.accept()
    active_connections[telegram_user_id] = websocket
    print(f"📡 WebSocket подключен: {telegram_user_id}")

    # Получаем все непрочитанные сообщения
    messages = await fetch_unread_messages(telegram_user_id)
    for message in messages:
        data_to_send = {
            "type": "new_message",
            "message_id": message["id"],
            "text": message["text"],
            "created_at": message["created_at"]
        }
        await websocket.send_json(data_to_send)
        print(f"Отправлено сообщение: {data_to_send}")

        # Ждём подтверждения от клиента
        confirmation = await websocket.receive_json()
        if confirmation.get("type") == "confirm" and confirmation.get("message_id") == message["id"]:
            success = await mark_message_as_processed(message["id"])
            if success:
                print(f"Сообщение {message['id']} подтверждено и отмечено как обработанное")
            else:
                print(f"Не удалось подтвердить сообщение {message['id']}")
        else:
            print("Получено неожиданное сообщение", confirmation)

    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print(f"❌ WebSocket отключен: {telegram_user_id}")
        del active_connections[telegram_user_id]


def start_api():
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    start_api()