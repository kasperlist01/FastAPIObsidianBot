import os
import torch
import asyncio
from faster_whisper import WhisperModel

# Устанавливаем оптимальное количество потоков (лучше 14-20 для Xeon E5-2690 v4)
num_threads = min(os.cpu_count(), 20)
torch.set_num_threads(num_threads)

_model = None  # Глобальная переменная для кеширования модели


def get_model():
    global _model
    if _model is None:
        model_size = "medium"  # Оптимальный баланс точности и скорости
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")  # float16 быстрее int8
    return _model


def _transcribe_audio_sync(audio_path: str) -> str:
    """
    Оптимизированная транскрибация с уменьшенным beam_size.
    """
    model = get_model()
    segments, info = model.transcribe(audio_path, beam_size=2)  # Уменьшенный beam_size для скорости
    transcription = " ".join(segment.text for segment in segments)
    return transcription.strip()  # Убираем лишние пробелы


async def transcribe_audio(audio_path: str) -> str:
    """
    Асинхронная обёртка для транскрибации аудио.
    """
    return await asyncio.to_thread(_transcribe_audio_sync, audio_path)
