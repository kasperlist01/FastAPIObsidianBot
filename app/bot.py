import os

import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from transcriber import transcribe_audio
from openai_client import generate_claude_response, generate_gpt_response

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FASTAPI_URL = os.getenv("FASTAPI_URL")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class PlanStates(StatesGroup):
    waiting_for_plan = State()
    plan_ready = State()
    editing_plan = State()


def get_plan_actions_inline_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="Отправить в Obsidian", callback_data="send_obsidian")
    kb.button(text="Изменить", callback_data="edit_plan")
    kb.adjust(1)
    return kb


async def get_moderated_text(text: str, state: FSMContext) -> str | tuple[str, str]:
    """
    Определяет, какую модель использовать (GPT или Cloud), и возвращает обработанный текст.
    """
    state_data = await state.get_data()
    model_choice = state_data.get("model", "cloud")
    if model_choice == "gpt":
        return await generate_gpt_response(text)
    return await generate_claude_response(text)


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """
    При старте выдаём приветственное сообщение и переводим в состояние ожидания плана.
    """
    await message.answer(
        "Привет! Я бот, который может принять от тебя голосовой план на день, "
        "расшифровать его и отправить в Obsidian.\n\n"
        "Просто отправь мне голосовое сообщение или введи текст.\n\n"
        "Также можешь установить модель обработки командой /gpt или /cloud (по умолчанию используется Cloud)."
    )
    await state.set_state(PlanStates.waiting_for_plan)


@dp.message(Command("gpt"))
async def set_gpt(message: Message, state: FSMContext):
    """
    Устанавливает использование GPT для обработки плана.
    """
    await state.update_data(model="gpt")
    await message.answer("✅ Модель обработки установлена: GPT")


@dp.message(Command("cloud"))
async def set_cloud(message: Message, state: FSMContext):
    """
    Устанавливает использование Cloud (Claude) для обработки плана.
    """
    await state.update_data(model="cloud")
    await message.answer("✅ Модель обработки установлена: Cloud")


@dp.message(F.content_type == "voice")
async def handle_voice_plan(message: Message, state: FSMContext):
    """
    Обрабатываем голосовое сообщение.
    Если состояние не установлено, считаем, что это новый план.
    Если состояние = editing_plan, то это изменение.
    """
    current_state = await state.get_state()
    if current_state is None:
        await state.set_state(PlanStates.waiting_for_plan)
        current_state = await state.get_state()

    # Сообщаем о начале обработки
    status_message = await message.answer("🎤 Получено голосовое сообщение. Идёт транскрибация...")

    # Скачиваем голосовой файл
    voice = message.voice
    file_info = await bot.get_file(voice.file_id)
    temp_file = f"temp_{voice.file_unique_id}.ogg"
    await bot.download_file(file_info.file_path, destination=temp_file)

    # Получаем исходный (транскрибированный) текст
    transcription = (await transcribe_audio(temp_file)).strip()
    os.remove(temp_file)

    # Определяем и получаем обработанный текст, используя выбранную модель
    plan_date, moderated_text = await get_moderated_text(transcription, state)

    # Сохраняем оба варианта в состоянии
    await state.update_data(original_text=transcription, moderated_text=moderated_text, plan_date=plan_date)

    kb = get_plan_actions_inline_keyboard().as_markup()

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=status_message.message_id,
        text="✅ Транскрибация и модерация завершены."
    )
    await message.answer(
        text=f"📝 Твой план на день (после модерации):\n\n{moderated_text}",
        reply_markup=kb
    )
    await state.set_state(PlanStates.plan_ready)


@dp.message(F.content_type == "text")
async def handle_text_plan(message: Message, state: FSMContext):
    """
    Обрабатываем текстовое сообщение.
    Если состояние не установлено, считаем, что это новый план.
    Если состояние = editing_plan, то это изменение.
    """
    current_state = await state.get_state()
    if current_state is None:
        await state.set_state(PlanStates.waiting_for_plan)
        current_state = await state.get_state()

    # Исходный текст, отправленный пользователем
    original_text = message.text.strip()
    if not original_text:
        await message.answer("Пожалуйста, отправьте непустой текст.")
        return

    # Определяем и получаем обработанный текст, используя выбранную модель
    plan_date, moderated_text = await get_moderated_text(original_text, state)

    # Сохраняем оба варианта в состоянии
    await state.update_data(original_text=original_text, moderated_text=moderated_text, plan_date=plan_date)

    kb = get_plan_actions_inline_keyboard().as_markup()
    await message.answer(
        text=f"📝 Твой план на день (после модерации):\n\n{moderated_text}",
        reply_markup=kb
    )
    await state.set_state(PlanStates.plan_ready)


@dp.callback_query(F.data == "send_obsidian", PlanStates.plan_ready)
async def send_to_obsidian_callback(query: CallbackQuery, state: FSMContext):
    """
    При нажатии на кнопку "Отправить в Obsidian" отправляем POST-запрос в FastAPI.
    Передаются оба варианта: исходное сообщение и обработанные данные.
    """
    await query.answer()

    data = await state.get_data()
    original_text = data.get("original_text", "")
    moderated_text = data.get("moderated_text", "")
    plan_date = data.get("plan_date", "")
    if not original_text or not moderated_text:
        await query.message.answer("Нет текста для отправки в Obsidian.")
        return

    telegram_user_id = str(query.from_user.id)
    progress_message = await query.message.answer("Отправляю план в Obsidian...")

    async with aiohttp.ClientSession() as session:
        params = {
            "telegram_user_id": telegram_user_id,
            "text": original_text,
            "model_text": moderated_text,
            "plan_date": plan_date,
            "progress_message_id": progress_message.message_id,
            "chat_id": query.message.chat.id,
        }
        async with session.post(f"{FASTAPI_URL}/messages", params=params) as response:
            resp_data = await response.json()

    await query.message.edit_text("✅ План успешно отправлен в Obsidian!")
    await state.clear()


@dp.callback_query(F.data == "edit_plan", PlanStates.plan_ready)
async def edit_plan_callback(query: CallbackQuery, state: FSMContext):
    """
    При нажатии на кнопку "Изменить" переводим пользователя в режим редактирования.
    """
    await query.answer()
    await query.message.answer("Отправь новый голосовой или введи другой текст для плана.")
    await state.set_state(PlanStates.editing_plan)


async def start_bot():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(start_bot())
