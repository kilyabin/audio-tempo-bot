"""
Telegram бот для изменения скорости и pitch аудио файлов
"""
import asyncio
import logging
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, TEMP_DIR, FILE_CLEANUP_HOURS, MAX_FILE_SIZE_BYTES, SUPPORTED_FORMATS
from audio_processor import AudioProcessor
from cleanup import cleanup_old_files

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Инициализация процессора аудио
audio_processor = AudioProcessor(TEMP_DIR)


class AudioProcessingStates(StatesGroup):
    """Состояния для обработки аудио"""
    waiting_for_custom_speed = State()


def create_speed_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками выбора скорости"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🐌 Slowed (-20%)", callback_data="speed_0.8"),
            InlineKeyboardButton(text="🚀 Speed Up (+20%)", callback_data="speed_1.2")
        ],
        [
            InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="speed_custom")
        ]
    ])
    return keyboard


@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        "🎵 <b>Бот для изменения скорости и pitch аудио</b>\n\n"
        "📤 Отправьте аудио или видео файл, и я помогу вам:\n"
        "• 🐌 Замедлить на 20% (slowed)\n"
        "• 🚀 Ускорить на 20% (speed up)\n"
        "• ✏️ Задать свою скорость (в формате 0.x)\n\n"
        "Поддерживаются форматы:\n"
        "🎵 MP3, WAV, FLAC, OGG, M4A, AAC, OPUS\n"
        "🎬 MP4, AVI, MOV, MKV, WEBM (аудио извлекается автоматически)",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "📖 <b>Помощь</b>\n\n"
        "🔹 Отправьте аудио или видео файл\n"
        "🔹 Выберите скорость изменения:\n"
        "   • 🐌 Slowed (-20%) - замедление на 20%\n"
        "   • 🚀 Speed Up (+20%) - ускорение на 20%\n"
        "   • ✏️ Ввести вручную - введите коэффициент (например, 0.8 или 1.5)\n\n"
        "💡 <b>Ручной ввод:</b>\n"
        "• 0.8 = замедление на 20%\n"
        "• 1.2 = ускорение на 20%\n"
        "• 0.5 = замедление в 2 раза\n"
        "• 2.0 = ускорение в 2 раза\n"
        "• Диапазон: от 0.1 до 5.0\n\n"
        "📁 <b>Поддерживаемые форматы:</b>\n"
        "🎵 Аудио: MP3, WAV, FLAC, OGG, M4A, AAC, OPUS\n"
        "🎬 Видео: MP4, AVI, MOV, MKV, WEBM\n"
        "(аудио извлекается автоматически)\n\n"
        "🗑️ Файлы автоматически удаляются через 24 часа",
        parse_mode="HTML"
    )


@dp.message(F.audio | F.voice | F.document | F.video | F.video_note)
async def handle_audio(message: Message, state: FSMContext):
    """Обработчик получения аудио или видео файла"""
    
    # Определяем тип файла и получаем file_id
    file_id = None
    file_name = None
    mime_type = None
    is_video = False
    file_size = None
    
    if message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio.mp3"
        mime_type = message.audio.mime_type
        file_size = message.audio.file_size
    elif message.voice:
        file_id = message.voice.file_id
        file_name = "voice.ogg"
        mime_type = "audio/ogg"
        file_size = message.voice.file_size
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
        mime_type = message.video.mime_type or "video/mp4"
        is_video = True
        file_size = message.video.file_size
    elif message.video_note:
        file_id = message.video_note.file_id
        file_name = "video_note.mp4"
        mime_type = "video/mp4"
        is_video = True
        file_size = message.video_note.file_size
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "file"
        mime_type = message.document.mime_type
        file_size = message.document.file_size
        
        # Проверяем, что это аудио или видео файл
        if mime_type:
            mime_lower = mime_type.lower()
            is_video = 'video' in mime_lower
            if not ('audio' in mime_lower or 'video' in mime_lower):
                # Проверяем расширение
                ext = Path(file_name).suffix.lower()
                video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp']
                audio_exts = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus', '.amr']
                
                if ext not in audio_exts + video_exts:
                    await message.answer(
                        "❌ Пожалуйста, отправьте аудио или видео файл.\n"
                        "Поддерживаются: MP3, WAV, FLAC, OGG, M4A, AAC, MP4, AVI, MOV, MKV и другие"
                    )
                    return
                is_video = ext in video_exts
        else:
            # Если mime_type не указан, определяем по расширению
            ext = Path(file_name).suffix.lower()
            video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp']
            audio_exts = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus', '.amr']
            
            if ext not in audio_exts + video_exts:
                await message.answer(
                    "❌ Пожалуйста, отправьте аудио или видео файл.\n"
                    "Поддерживаются: MP3, WAV, FLAC, OGG, M4A, AAC, MP4, AVI, MOV, MKV и другие"
                )
                return
            is_video = ext in video_exts
    
    if not file_id:
        await message.answer("❌ Не удалось получить файл")
        return
    
    # Проверяем размер файла (сначала из message, потом из API)
    if file_size and file_size > MAX_FILE_SIZE_BYTES:
        await message.answer(
            f"❌ Файл слишком большой ({file_size / 1024 / 1024:.1f} МБ). "
            f"Максимальный размер: {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} МБ"
        )
        return
    
    # Пытаемся получить информацию о файле из API (для получения file_path)
    try:
        file_info = await bot.get_file(file_id)
        # Дополнительная проверка размера на случай, если его не было в message
        if file_info.file_size and file_info.file_size > MAX_FILE_SIZE_BYTES:
            await message.answer(
                f"❌ Файл слишком большой ({file_info.file_size / 1024 / 1024:.1f} МБ). "
                f"Максимальный размер: {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} МБ"
            )
            return
    except Exception as e:
        error_str = str(e).lower()
        # Проверяем, является ли это ошибкой о большом размере файла
        if "too big" in error_str or "file is too big" in error_str:
            await message.answer(
                f"❌ Файл слишком большой для загрузки ботом.\n"
                f"Максимальный размер: {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} МБ\n\n"
                f"💡 Попробуйте:\n"
                f"• Отправить файл меньшего размера\n"
                f"• Сжать файл перед отправкой"
            )
            logger.warning(f"Файл слишком большой для Telegram API: {file_name}")
            return
        else:
            logger.error(f"Ошибка при получении информации о файле: {e}")
            await message.answer(
                "❌ Не удалось получить информацию о файле. "
                "Попробуйте отправить файл заново."
            )
            return
    
    # Для видео файлов определяем имя выходного аудио файла
    if is_video:
        # Заменяем расширение на .mp3 или .m4a
        original_path = Path(file_name)
        file_name = f"{original_path.stem}.mp3"
    
    # Сохраняем информацию о файле в состоянии
    await state.update_data(
        file_id=file_id,
        file_name=file_name,
        mime_type=mime_type,
        is_video=is_video
    )
    
    # Показываем клавиатуру выбора скорости
    file_type = "🎬 видео" if is_video else "🎵 аудио"
    await message.answer(
        f"✅ Файл получен: <b>{Path(file_name).name}</b> ({file_type})\n\n"
        "Выберите действие:",
        reply_markup=create_speed_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("speed_"))
async def handle_speed_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора скорости"""
    
    data = callback.data
    user_data = await state.get_data()
    
    if not user_data.get("file_id"):
        await callback.answer("❌ Файл не найден. Отправьте файл заново.", show_alert=True)
        return
    
    if data == "speed_custom":
        # Запрашиваем ручной ввод
        await callback.message.edit_text(
            "✏️ <b>Введите коэффициент скорости</b>\n\n"
            "Примеры:\n"
            "• <code>0.8</code> - замедление на 20%\n"
            "• <code>1.2</code> - ускорение на 20%\n"
            "• <code>0.5</code> - замедление в 2 раза\n"
            "• <code>2.0</code> - ускорение в 2 раза\n\n"
            "Введите число от 0.1 до 5.0:",
            parse_mode="HTML"
        )
        await state.set_state(AudioProcessingStates.waiting_for_custom_speed)
        await callback.answer()
        return
    
    # Извлекаем коэффициент скорости
    try:
        speed_factor = float(data.replace("speed_", ""))
    except ValueError:
        await callback.answer("❌ Ошибка в данных", show_alert=True)
        return
    
    await callback.answer("⏳ Обрабатываю файл...")
    await process_audio_file(callback.message, state, speed_factor, user_data)


@dp.message(AudioProcessingStates.waiting_for_custom_speed)
async def handle_custom_speed_input(message: Message, state: FSMContext):
    """Обработчик ручного ввода скорости"""
    
    try:
        speed_factor = float(message.text.strip())
        
        # Проверяем диапазон
        if speed_factor < 0.1 or speed_factor > 5.0:
            await message.answer(
                "❌ Коэффициент должен быть от 0.1 до 5.0\n"
                "Попробуйте еще раз:"
            )
            return
        
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число (например, 0.8 или 1.2)\n"
            "Попробуйте еще раз:"
        )
        return
    
    user_data = await state.get_data()
    await state.clear()
    
    if not user_data.get("file_id"):
        await message.answer("❌ Файл не найден. Отправьте файл заново.")
        return
    
    processing_msg = await message.answer("⏳ Обрабатываю файл...")
    await process_audio_file(processing_msg, state, speed_factor, user_data)


async def process_audio_file(message: Message, state: FSMContext, speed_factor: float, user_data: dict):
    """Обрабатывает аудио или видео файл"""
    
    file_id = user_data["file_id"]
    file_name = user_data["file_name"]
    is_video = user_data.get("is_video", False)
    
    input_path = None
    output_path = None
    
    try:
        # Получаем информацию о файле и скачиваем
        try:
            file_info = await bot.get_file(file_id)
        except Exception as e:
            error_str = str(e).lower()
            if "too big" in error_str or "file is too big" in error_str:
                await message.edit_text(
                    f"❌ Файл слишком большой для загрузки ботом.\n"
                    f"Максимальный размер: {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} МБ\n\n"
                    f"💡 Попробуйте отправить файл меньшего размера"
                )
                return
            else:
                raise
        
        # Определяем расширение входного файла
        original_ext = Path(file_info.file_path).suffix if hasattr(file_info, 'file_path') and file_info.file_path else Path(file_name).suffix
        if not original_ext:
            original_ext = ".mp4" if is_video else ".mp3"
        
        input_path = TEMP_DIR / f"input_{file_id.replace('/', '_').replace('\\', '_')}{original_ext}"
        
        await message.edit_text("📥 Скачиваю файл...")
        
        try:
            await bot.download_file(file_info.file_path, input_path)
        except Exception as e:
            error_str = str(e).lower()
            if "too big" in error_str or "file is too big" in error_str:
                await message.edit_text(
                    f"❌ Файл слишком большой для загрузки.\n"
                    f"Максимальный размер: {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} МБ"
                )
                return
            else:
                raise
        
        # Если это видео, сначала извлекаем аудио
        if is_video:
            await message.edit_text("🎬 Извлекаю аудио из видео...")
            audio_extracted_path = TEMP_DIR / f"extracted_{file_id.replace('/', '_')}.wav"
            
            if not audio_processor.extract_audio_from_video(input_path, audio_extracted_path):
                await message.edit_text("❌ Не удалось извлечь аудио из видео. Проверьте формат файла.")
                if input_path.exists():
                    input_path.unlink()
                return
            
            # Удаляем исходное видео и используем извлеченное аудио
            if input_path.exists():
                input_path.unlink()
            input_path = audio_extracted_path
        
        # Определяем имя выходного файла
        output_path = TEMP_DIR / audio_processor.get_output_filename(file_name, speed_factor)
        
        await message.edit_text("🎵 Обрабатываю аудио...")
        
        # Обрабатываем аудио (передаем оригинальное имя файла для метаданных)
        success = audio_processor.process_audio(input_path, speed_factor, output_path, original_filename=file_name)
        
        if not success:
            await message.edit_text("❌ Ошибка при обработке файла. Попробуйте другой файл.")
            # Удаляем входной файл
            if input_path.exists():
                input_path.unlink()
            return
        
        # Отправляем обработанный файл
        await message.edit_text("📤 Отправляю файл...")
        
        # Проверяем, можно ли воспроизвести файл напрямую в Telegram
        if not audio_processor.is_telegram_playable_format(output_path):
            # Конвертируем в MP3 для отправки в Telegram
            mp3_path = TEMP_DIR / f"{output_path.stem}.mp3"
            await message.edit_text("🔄 Конвертирую в MP3 для Telegram...")
            
            if audio_processor.convert_to_mp3_for_telegram(output_path, mp3_path):
                # Сначала отправляем MP3 для воспроизведения
                mp3_filename = Path(output_path.name).stem + ".mp3"
                mp3_file = FSInputFile(mp3_path, filename=mp3_filename)
                
                try:
                    await message.answer_audio(
                        mp3_file,
                        caption=f"✅ <b>Готово! MP3 версия</b>\n\n"
                               f"Файл: {mp3_filename}\n"
                               f"Коэффициент: {speed_factor:.2f} ({int((speed_factor - 1) * 100):+d}%)",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    # Если не получилось отправить как audio, отправляем как document
                    logger.warning(f"Не удалось отправить MP3 как audio, отправляем как document: {e}")
                    await message.answer_document(
                        mp3_file,
                        caption=f"✅ <b>Готово! MP3 версия</b>\n\n"
                               f"Файл: {mp3_filename}\n"
                               f"Коэффициент: {speed_factor:.2f} ({int((speed_factor - 1) * 100):+d}%)",
                        parse_mode="HTML"
                    )
                
                # Затем отправляем оригинальный формат (FLAC)
                await asyncio.sleep(0.5)  # Небольшая задержка между отправками
                original_file = FSInputFile(output_path, filename=output_path.name)
                await message.answer_document(
                    original_file,
                    caption=f"📁 <b>Оригинальный формат</b>\n\n"
                           f"Файл: {output_path.name}\n"
                           f"Коэффициент: {speed_factor:.2f} ({int((speed_factor - 1) * 100):+d}%)",
                    parse_mode="HTML"
                )
                
                # Удаляем временный MP3 файл после отправки
                try:
                    mp3_path.unlink()
                    logger.debug(f"Удален временный MP3 файл: {mp3_path}")
                except:
                    pass
            else:
                # Если не удалось сконвертировать, отправляем только оригинальный файл
                logger.warning(f"Не удалось сконвертировать {output_path} в MP3")
                original_file = FSInputFile(output_path, filename=output_path.name)
                await message.answer_document(
                    original_file,
                    caption=f"✅ <b>Готово!</b>\n\n"
                           f"Файл: {output_path.name}\n"
                           f"Коэффициент: {speed_factor:.2f} ({int((speed_factor - 1) * 100):+d}%)",
                    parse_mode="HTML"
                )
        else:
            # Формат поддерживается для прямого воспроизведения
            audio_file = FSInputFile(output_path, filename=output_path.name)
            
            # Если это MP3, отправляем как audio для прямого воспроизведения
            if output_path.suffix.lower() == '.mp3':
                try:
                    await message.answer_audio(
                        audio_file,
                        caption=f"✅ <b>Готово!</b>\n\n"
                               f"Файл: {output_path.name}\n"
                               f"Коэффициент: {speed_factor:.2f} ({int((speed_factor - 1) * 100):+d}%)",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    # Если не получилось отправить как audio, отправляем как document
                    logger.warning(f"Не удалось отправить как audio, отправляем как document: {e}")
                    await message.answer_document(
                        audio_file,
                        caption=f"✅ <b>Готово!</b>\n\n"
                               f"Файл: {output_path.name}\n"
                               f"Коэффициент: {speed_factor:.2f} ({int((speed_factor - 1) * 100):+d}%)",
                        parse_mode="HTML"
                    )
            else:
                # Для других поддерживаемых форматов (OGG, M4A) отправляем как document
                await message.answer_document(
                    audio_file,
                    caption=f"✅ <b>Готово!</b>\n\n"
                           f"Файл: {output_path.name}\n"
                           f"Коэффициент: {speed_factor:.2f} ({int((speed_factor - 1) * 100):+d}%)",
                    parse_mode="HTML"
                )
        
        await message.delete()
        
        logger.info(f"Файл обработан: {file_name} -> {output_path.name} (speed: {speed_factor})")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}", exc_info=True)
        try:
            await message.edit_text("❌ Произошла ошибка при обработке файла. Попробуйте еще раз.")
        except:
            await message.answer("❌ Произошла ошибка при обработке файла. Попробуйте еще раз.")
    finally:
        # Удаляем временные файлы
        if input_path and input_path.exists():
            try:
                input_path.unlink()
            except:
                pass
        await state.clear()


async def periodic_cleanup():
    """Периодическая очистка старых файлов"""
    while True:
        try:
            await asyncio.sleep(3600)  # Каждый час
            cleanup_old_files(TEMP_DIR, FILE_CLEANUP_HOURS)
        except Exception as e:
            logger.error(f"Ошибка в periodic_cleanup: {e}", exc_info=True)


async def main():
    """Основная функция"""
    logger.info("Запуск бота...")
    
    # Проверяем наличие BOT_TOKEN
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Установите его в .env файле.")
        return
    
    # Запускаем задачу очистки файлов
    asyncio.create_task(periodic_cleanup())
    
    # Первичная очистка при старте
    cleanup_old_files(TEMP_DIR, FILE_CLEANUP_HOURS)
    
    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")


