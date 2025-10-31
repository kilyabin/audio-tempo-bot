"""
Модуль для очистки старых файлов
"""
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def cleanup_old_files(temp_dir: Path, max_age_hours: int = 24):
    """
    Удаляет файлы старше указанного времени
    
    Args:
        temp_dir: Директория с временными файлами
        max_age_hours: Максимальный возраст файла в часах
    """
    if not temp_dir.exists():
        return
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    deleted_count = 0
    total_size = 0
    
    try:
        for file_path in temp_dir.iterdir():
            if file_path.is_file():
                # Получаем время модификации файла
                file_age = current_time - file_path.stat().st_mtime
                
                if file_age > max_age_seconds:
                    # Файл слишком старый, удаляем
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    deleted_count += 1
                    total_size += file_size
                    logger.debug(f"Удален старый файл: {file_path.name} ({file_age/3600:.1f} часов)")
    
    except Exception as e:
        logger.error(f"Ошибка при очистке файлов: {e}", exc_info=True)
    
    if deleted_count > 0:
        logger.info(
            f"Очистка завершена: удалено {deleted_count} файлов, "
            f"освобождено {total_size / 1024 / 1024:.2f} МБ"
        )


