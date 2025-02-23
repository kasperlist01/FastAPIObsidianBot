import datetime
import os
import openai
import asyncio
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# Загружаем переменные окружения
load_dotenv()

# Получаем API-ключ и URL OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = os.getenv("OPENAI_API_URL")
PROMT_PATH = os.getenv("PROMT_PATH")

# Проверяем, заданы ли ключ и URL
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не задан. Укажите ключ в .env файле.")

# Настраиваем OpenAI
client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_URL)

def read_prompt_from_file(filename: str) -> str:
    """Читает текстовый файл и возвращает его содержимое."""
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return "Ошибка: файл с промтом не найден."
    except Exception as e:
        return f"Ошибка при чтении файла: {str(e)}"

async def generate_response(text, model: str = "gpt-4", temperature: float = 0.7) -> str:
    """
    Отправляет асинхронный запрос в OpenAI API и получает ответ.

    Args:
        text (str): Входящий запрос пользователя.
        model (str): Выбранная модель OpenAI (по умолчанию gpt-4).
        temperature (float): Температура генерации ответа.

    Returns:
        str: Ответ от модели.
    """
    prompt = read_prompt_from_file(PROMT_PATH)

    # Получаем текущую дату и время в Московском часовом поясе (UTC+3)
    now_moscow = datetime.datetime.now(ZoneInfo("Europe/Moscow"))

    # Форматируем дату
    formatted_date = now_moscow.strftime("%d-%ое %B %Y, %H:%M по Москве")

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": f'Сегодня {formatted_date}\n{prompt}'},
                {"role": "user", "content": text}
            ],
            temperature=temperature
        )
        return response.choices[0].message.content
    except openai.OpenAIError as e:
        return f"Ошибка OpenAI API: {str(e)}"
    except Exception as e:
        return f"Ошибка обработки сообщения: {str(e)}"

async def main():
    text = '111'
    response = await generate_response(text)
    print(response)

# Запускаем пример
if __name__ == "__main__":
    asyncio.run(main())
