import datetime
import os

import openai
import asyncio
import anthropic
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# Загружаем переменные окружения
load_dotenv()

# Получаем API-ключ и URL OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = os.getenv("OPENAI_API_URL")
PROMT_PATH = os.getenv("PROMT_PATH")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не задан. Укажите ключ в .env файле.")

# Настраиваем OpenAI-клиент
client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_URL)

# Получаем API-ключ и URL для Anthropic (Claude)
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_API_URL = os.getenv("ANTHROPIC_API_URL")

if not CLAUDE_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY не задан. Укажите ключ в .env файле.")

# Настраиваем клиент для Anthropic (Claude)
claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY, base_url=CLAUDE_API_URL)


def read_prompt_from_file(filename: str) -> str:
    """Читает текстовый файл и возвращает его содержимое."""
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return "Ошибка: файл с промтом не найден."
    except Exception as e:
        return f"Ошибка при чтении файла: {str(e)}"


def generate_week_dates() -> dict:
    """Создает словарь с датами на неделю вперёд."""
    now = datetime.datetime.now(ZoneInfo("Europe/Moscow"))
    week_dates = {}
    for i in range(7):
        future_date = now + datetime.timedelta(days=i)
        week_dates[future_date.strftime("%A")] = {
            "day": future_date.strftime("%d"),
            "month": future_date.strftime("%B"),
            "year": future_date.strftime("%Y"),
        }
    return week_dates


async def generate_gpt_response(text, model: str = "gpt-4o", temperature: float = 0.7) -> str | tuple[str, str]:
    """
    Отправляет асинхронный запрос в OpenAI API и получает ответ.
    """
    prompt = read_prompt_from_file(PROMT_PATH)
    now_moscow = datetime.datetime.now(ZoneInfo("Europe/Moscow"))
    formatted_date = now_moscow.strftime("%A, %d-%ое %B %Y, %H:%M по Москве")
    week_dates = generate_week_dates()

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": f"Сегодня {formatted_date}\nДаты на неделю: {week_dates}\n{prompt}"},
                {"role": "user", "content": text}
            ],
            temperature=temperature
        )

        result = response.choices[0].message.content
        date, result = result.split('//')
        marker = "📅 Дневной план"
        date = date.replace('{{', '').replace('}}', '')
        idx = result.find(marker)
        if idx != -1:
            result = result[idx:]
        return date, result
    except openai.OpenAIError as e:
        return f"Ошибка OpenAI API: {str(e)}"
    except Exception as e:
        return f"Ошибка обработки сообщения: {str(e)}"


async def generate_claude_response(text, model: str = "claude-3-5-sonnet-20240620", temperature: float = 0.7) -> tuple[
    str, str]:
    """
    Отправляет асинхронный запрос в API Anthropic (Claude) и получает ответ.
    """
    prompt = read_prompt_from_file(PROMT_PATH)
    now_moscow = datetime.datetime.now(ZoneInfo("Europe/Moscow"))
    formatted_date = now_moscow.strftime("%A, %d-%ое %B %Y, %H:%M по Москве")
    week_dates = generate_week_dates()

    conversation = (
        f"Human: Сегодня {formatted_date}\nДаты на неделю: {week_dates}\n{prompt}\n\n"
        f"Human: {text}\n\n"
        "Assistant:"
    )

    def claude_request():
        try:
            response = claude_client.messages.create(
                model=model,
                max_tokens=4096,
                temperature=temperature,
                messages=[{"role": "user", "content": conversation}]
            )
            return response.content[0].text
        except Exception as e:
            return f"Ошибка Anthropic API: {str(e)}"

    result = await asyncio.to_thread(claude_request)
    date, result = result.split("//")
    marker = "📅 Дневной план"
    date = date.replace('{{', '').replace('}}', '')
    idx = result.find(marker)
    if idx != -1:
        result = result[idx:]
    return date, result


async def main():
    text = "Привет, как дела?"
    print("Ответ от OpenAI:")
    response_openai = await generate_gpt_response(text)
    print(response_openai)
    print("\nОтвет от Anthropic (Claude):")
    response_claude = await generate_claude_response(text)
    print(response_claude)


if __name__ == "__main__":
    asyncio.run(main())