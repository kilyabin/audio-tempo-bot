"""
Конфигурация бота
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Путь к временной папке
TEMP_DIR = Path(__file__).parent / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# Время хранения файлов (в часах)
FILE_CLEANUP_HOURS = int(os.getenv("FILE_CLEANUP_HOURS", "24"))

# Максимальный размер файла (в МБ)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Поддерживаемые форматы аудио
SUPPORTED_FORMATS = {
    'audio/mpeg', 'audio/mp3', 'audio/mpeg3', 'audio/x-mpeg-3',
    'audio/wav', 'audio/x-wav', 'audio/wave',
    'audio/flac', 'audio/x-flac',
    'audio/ogg', 'audio/ogg; codecs=opus', 'audio/opus',
    'audio/m4a', 'audio/x-m4a', 'audio/mp4',
    'audio/aac',
    'audio/x-ms-wma',
    'audio/webm',
}


