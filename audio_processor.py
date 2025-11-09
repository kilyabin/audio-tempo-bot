"""
Модуль для обработки аудио: изменение скорости и pitch
"""
import os
import json
import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Класс для обработки аудио файлов"""
    
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(exist_ok=True)
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """Проверяет наличие ffmpeg в системе"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("ffmpeg не найден. Убедитесь, что ffmpeg установлен в системе.")
    
    def _detect_audio_format(self, file_path: Path) -> str:
        """Определяет формат аудио файла"""
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0',
                 '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1',
                 str(file_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Не удалось определить формат: {e}")
        return None
    
    def _get_sample_rate(self, file_path: Path) -> int:
        """Получает sample rate аудио файла"""
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0',
                 '-show_entries', 'stream=sample_rate', '-of', 'default=noprint_wrappers=1:nokey=1',
                 str(file_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                try:
                    return int(result.stdout.strip())
                except ValueError:
                    pass
        except Exception as e:
            logger.debug(f"Не удалось получить sample rate: {e}")
        return None
    
    def _get_metadata(self, file_path: Path) -> dict:
        """Получает все метаданные из аудио файла"""
        metadata = {}
        try:
            # Получаем все метаданные в формате JSON
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format_tags=all',
                 '-of', 'json', str(file_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    tags = data.get('format', {}).get('tags', {})
                    if tags:
                        # Копируем все теги
                        metadata = tags.copy()
                except (json.JSONDecodeError, KeyError):
                    pass
        except Exception as e:
            logger.debug(f"Не удалось получить метаданные: {e}")
        return metadata
    
    def process_audio(self, input_path: Path, speed_factor: float, output_path: Path, original_filename: str = None) -> bool:
        """
        Изменяет скорость и pitch аудио файла
        
        Args:
            input_path: Путь к исходному файлу
            speed_factor: Коэффициент скорости (1.0 = оригинал, 0.8 = -20%, 1.2 = +20%)
            output_path: Путь для сохранения обработанного файла
            original_filename: Оригинальное имя файла (для использования в метаданных, если нет title)
        
        Returns:
            True если успешно, False при ошибке
        """
        if not input_path.exists():
            logger.error(f"Входной файл не существует: {input_path}")
            return False
        
        try:
            logger.info(f"Обработка аудио: {input_path} -> {output_path} (speed: {speed_factor})")
            
            # Определяем формат выходного файла и параметры кодека
            output_ext = output_path.suffix.lower()
            codec_params = self._get_codec_params(output_ext)
            
            # Получаем текущий sample rate файла
            current_sr = self._get_sample_rate(input_path)
            if current_sr is None:
                # Если не удалось определить, используем стандартный
                current_sr = 44100
                logger.warning(f"Не удалось определить sample rate для {input_path}, используем 44100")
            
            # Изменяем sample rate - это изменит и скорость, и pitch одновременно
            # Для одновременного изменения скорости и pitch используем asetrate + aresample
            # asetrate изменяет скорость воспроизведения и pitch, aresample возвращает к нормальному sample rate
            new_sample_rate = int(current_sr * speed_factor)
            
            # Используем asetrate для изменения скорости/pitch, затем aresample для нормализации sample rate
            filter_complex = f"asetrate={new_sample_rate},aresample={current_sr}"
            
            # Получаем метаданные из исходного файла
            metadata = self._get_metadata(input_path)
            
            # Определяем, что добавить к названию
            if speed_factor < 1.0:
                speed_tag = " (Slowed)"
            elif speed_factor > 1.0:
                speed_tag = " (Speed Up)"
            else:
                speed_tag = ""
            
            # Обновляем title в метаданных
            original_title = metadata.get('title', '')
            if original_title:
                # Убираем старые теги из title, если они есть
                title_clean = original_title.replace(" (Slowed)", "").replace(" (Speed Up)", "").strip()
                
                # Извлекаем только название трека, удаляя исполнителя из title
                # Обычные форматы: "Artist - Title", "Artist: Title", "Artist | Title"
                song_title = title_clean
                
                # Список всех возможных разделителей (с пробелами и без)
                separators = [
                    ' - ', ' – ', ' — ',  # Тире с пробелами
                    ' : ', ': ', ' | ', ' / ',  # Другие разделители
                    '- ', '– ', '— ',  # Тире только с пробелом справа
                    ' -', ' –', ' —',  # Тире только с пробелом слева
                    ':', '|', '/',  # Без пробелов
                ]
                
                # Если есть отдельное поле artist, ОБЯЗАТЕЛЬНО удаляем его из title
                artist_name = metadata.get('artist', '').strip()
                if artist_name:
                    # Нормализуем для сравнения (убираем лишние пробелы, приводим к нижнему регистру)
                    artist_normalized = ' '.join(artist_name.lower().split())
                    title_normalized = title_clean.lower()
                    
                    # Пытаемся найти и удалить artist в разных вариациях
                    found_and_removed = False
                    
                    # Вариант 1: "Artist - Title" или "Artist: Title" и т.д.
                    for sep in separators:
                        sep_normalized = sep.strip()
                        # Проверяем начало строки
                        pattern_variants = [
                            artist_name + sep,
                            artist_name.lower() + sep,
                            artist_name.upper() + sep,
                            artist_name.title() + sep,
                        ]
                        
                        for pattern in pattern_variants:
                            if title_clean.startswith(pattern):
                                song_title = title_clean[len(pattern):].strip()
                                found_and_removed = True
                                break
                        
                        if found_and_removed:
                            break
                        
                        # Проверяем конец строки: "Title - Artist"
                        pattern_variants = [
                            sep + artist_name,
                            sep + artist_name.lower(),
                            sep + artist_name.upper(),
                            sep + artist_name.title(),
                        ]
                        
                        for pattern in pattern_variants:
                            if title_clean.endswith(pattern):
                                song_title = title_clean[:-len(pattern):].strip()
                                found_and_removed = True
                                break
                        
                        if found_and_removed:
                            break
                    
                    # Вариант 2: Если не нашли с разделителями, ищем artist в начале без учета регистра
                    if not found_and_removed:
                        title_lower = title_clean.lower()
                        artist_lower = artist_name.lower()
                        
                        # Проверяем, начинается ли title с artist (с разделителем или без)
                        if title_lower.startswith(artist_lower):
                            # Находим где заканчивается artist в оригинальном title
                            # Ищем позицию после artist
                            remaining_pos = len(artist_name)
                            
                            # Пропускаем пробелы и разделители после artist
                            while remaining_pos < len(title_clean) and (
                                title_clean[remaining_pos] in ' \t' or
                                title_clean[remaining_pos:remaining_pos+2] in [' -', ' –', ' —', ' :', ' |', ' /']
                            ):
                                remaining_pos += 1
                            
                            if remaining_pos < len(title_clean):
                                song_title = title_clean[remaining_pos:].strip()
                                # Убираем разделители в начале, если остались
                                while song_title and song_title[0] in '-–—:|/':
                                    song_title = song_title[1:].strip()
                                found_and_removed = True
                    
                    # Если все еще не удалили, пробуем через регулярное выражение или простое удаление
                    if not found_and_removed or song_title == title_clean:
                        # Последняя попытка: удаляем все до первого разделителя, если первая часть похожа на artist
                        for sep in separators:
                            if sep in title_clean:
                                parts = title_clean.split(sep, 1)
                                if len(parts) == 2:
                                    part1, part2 = parts[0].strip(), parts[1].strip()
                                    # Если первая часть совпадает с artist (с учетом регистра)
                                    if part1.lower() == artist_lower:
                                        song_title = part2
                                        found_and_removed = True
                                        break
                                    # Или если первая часть короткая и вторая длинная (скорее всего artist - title)
                                    elif len(part1) < 30 and len(part2) > len(part1):
                                        song_title = part2
                                        found_and_removed = True
                                        break
                
                # Если не удалось извлечь через artist, пробуем общий подход
                # Ищем первый разделитель и берем часть после него (или более длинную часть)
                if song_title == title_clean:
                    best_match = None
                    best_position = -1
                    
                    for sep in separators:
                        if sep in title_clean:
                            parts = title_clean.split(sep, 1)
                            if len(parts) == 2:
                                part1, part2 = parts[0].strip(), parts[1].strip()
                                # Предпочитаем более длинную часть как название трека
                                # Но если первая часть явно короче и похожа на имя, берем вторую
                                if len(part2) > len(part1) or len(part1) < 20:
                                    if best_position < title_clean.index(sep):
                                        best_match = part2
                                        best_position = title_clean.index(sep)
                    
                    if best_match:
                        song_title = best_match
                
                # Если есть artist в метаданных, но мы все еще не удалили его из title,
                # применяем принудительное удаление - берем все после первого разделителя
                if artist_name and song_title == title_clean:
                    # Принудительно ищем первый разделитель и берем часть после него
                    for sep in separators:
                        if sep in title_clean:
                            parts = title_clean.split(sep, 1)
                            if len(parts) == 2:
                                song_title = parts[1].strip()
                                logger.debug(f"Принудительно извлечен title после разделителя '{sep}': {song_title}")
                                break
                
                # Финальная проверка: если title все еще содержит artist (по подстроке), удаляем его
                if artist_name and artist_name.lower() in song_title.lower() and song_title != title_clean:
                    # Если в извлеченном title все еще есть artist, пробуем удалить
                    parts = song_title.split(artist_name, 1)
                    if len(parts) == 2:
                        # Берем часть без artist
                        remaining = (parts[0] + parts[1]).strip()
                        # Убираем разделители в начале
                        while remaining and remaining[0] in '-–—:|/ ':
                            remaining = remaining[1:].strip()
                        if remaining:
                            song_title = remaining
                
                # Если все еще не изменилось, оставляем как есть
                new_title = song_title + speed_tag
            elif original_filename:
                # Если нет title, но есть оригинальное имя файла, используем его
                stem_clean = Path(original_filename).stem.replace(" (Slowed)", "").replace(" (Speed Up)", "").strip()
                new_title = stem_clean + speed_tag
            else:
                # Если нет ни title, ни оригинального имени файла, не добавляем title в метаданные
                new_title = None
            
            # Собираем список метаданных для добавления
            # ВАЖНО: НЕ используем -map_metadata, чтобы старый title не копировался
            # Это гарантирует, что в выходном файле будет только наш новый title
            metadata_params = []
            
            # Явно передаем все метаданные из исходного файла, ИСКЛЮЧАЯ title
            # Это сохраняет artist, album и другие метаданные, но НЕ title
            for key, value in metadata.items():
                if value:  # Пропускаем пустые значения
                    # НЕ передаем title, так как он будет обновлен
                    if key.lower() != 'title':
                        # Экранируем значения метаданных для командной строки
                        # Заменяем специальные символы, которые могут вызвать проблемы
                        value_str = str(value).replace('\\', '\\\\').replace(':', '\\:').replace('=', '\\=')
                        metadata_params.extend(['-metadata', f'{key}={value_str}'])
            
            # В конце добавляем НОВЫЙ title (это ЕДИНСТВЕННЫЙ title в файле)
            if new_title:
                # Экранируем title тоже
                title_str = new_title.replace('\\', '\\\\').replace(':', '\\:').replace('=', '\\=')
                metadata_params.extend(['-metadata', f'title={title_str}'])
            
            # Собираем команду ffmpeg
            # Используем -map_metadata -1 чтобы НЕ копировать метаданные автоматически
            # и добавляем только те, которые мы явно указали
            cmd = [
                'ffmpeg',
                '-i', str(input_path),
                '-map_metadata', '-1',  # НЕ копируем метаданные из исходного файла
                '-af', filter_complex,
                '-ar', str(current_sr),  # Устанавливаем sample rate вывода
                *metadata_params,  # Добавляем только наши метаданные (без старого title)
                *codec_params,
                '-y',  # Перезаписывать выходной файл
                str(output_path)
            ]
            
            logger.debug(f"Выполнение команды: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300  # Максимум 5 минут на обработку
            )
            
            if result.returncode != 0:
                logger.error(f"Ошибка ffmpeg: {result.stderr}")
                return False
            
            # Проверяем, что выходной файл создан
            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error("Выходной файл не создан или пуст")
                return False
            
            logger.info(f"Аудио успешно обработано: {output_path} ({output_path.stat().st_size / 1024:.2f} КБ)")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Превышено время обработки файла (5 минут)")
            return False
        except Exception as e:
            logger.error(f"Ошибка при обработке аудио: {e}", exc_info=True)
            return False
    
    def _get_codec_params(self, extension: str) -> list:
        """Возвращает параметры кодека для формата"""
        extension = extension.lower()
        
        params_map = {
            '.mp3': [
                '-acodec', 'libmp3lame', 
                '-q:a', '2',  # Качество ~192 kbps
                '-id3v2_version', '3',  # Используем ID3v2.3 для лучшей совместимости
                '-write_id3v2', '1',  # Включаем запись ID3v2 тегов
            ],
            '.m4a': ['-acodec', 'aac', '-b:a', '192k'],
            '.ogg': ['-acodec', 'libvorbis', '-q:a', '5'],   # Качество ~160 kbps
            '.flac': ['-acodec', 'flac', '-compression_level', '5'],
            '.wav': ['-acodec', 'pcm_s16le'],
            '.opus': ['-acodec', 'libopus', '-b:a', '128k'],
            '.aac': ['-acodec', 'aac', '-b:a', '192k'],
        }
        
        # Для неизвестных форматов используем MP3 как fallback
        fallback_params = [
            '-acodec', 'libmp3lame', 
            '-q:a', '2',
            '-id3v2_version', '3',
            '-write_id3v2', '1',
        ]
        return params_map.get(extension, fallback_params)
    
    def extract_audio_from_video(self, video_path: Path, output_path: Path) -> bool:
        """
        Извлекает аудио из видео файла
        
        Args:
            video_path: Путь к видео файлу
            output_path: Путь для сохранения извлеченного аудио
        
        Returns:
            True если успешно, False при ошибке
        """
        if not video_path.exists():
            logger.error(f"Видео файл не существует: {video_path}")
            return False
        
        try:
            logger.info(f"Извлечение аудио из видео: {video_path}")
            
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-vn',  # Без видео
                '-acodec', 'pcm_s16le',  # WAV формат
                '-ar', '44100',  # Sample rate
                '-ac', '2',  # Стерео
                '-y',
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                logger.error(f"Ошибка при извлечении аудио: {result.stderr}")
                return False
            
            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error("Извлеченный аудио файл пуст или не создан")
                return False
            
            logger.info(f"Аудио успешно извлечено: {output_path}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Превышено время извлечения аудио (5 минут)")
            return False
        except Exception as e:
            logger.error(f"Ошибка при извлечении аудио: {e}", exc_info=True)
            return False
    
def get_output_filename(self, original_filename: str, speed_factor: float) -> str:
    path = Path(original_filename)
    stem = path.stem
    suffix = path.suffix

    if speed_factor < 1.0:
        speed_tag = " (Slowed)"
    elif speed_factor > 1.0:
        speed_tag = " (Speed Up)"
    else:
        speed_tag = ""

    stem_clean = stem.replace(" (Slowed)", "").replace(" (Speed Up)", "").strip()
    new_stem = stem_clean + speed_tag

    # Также добавляем процент для совместимости
    speed_percent = int((speed_factor - 1.0) * 100)
    if speed_percent != 0:
        # добавляем знак + для положительных значений автоматически
        speed_str = f" {speed_percent:+d}%"
    else:
        speed_str = ""

    return f"{new_stem}{speed_str}{suffix}"
        
        return f"{new_stem}{speed_str}{suffix}"
    
    def convert_to_mp3_for_telegram(self, input_path: Path, output_path: Path) -> bool:
        """
        Конвертирует аудио файл в MP3 для отправки в Telegram
        
        Args:
            input_path: Путь к исходному файлу
            output_path: Путь для сохранения MP3 файла
        
        Returns:
            True если успешно, False при ошибке
        """
        if not input_path.exists():
            logger.error(f"Входной файл не существует: {input_path}")
            return False
        
        try:
            logger.info(f"Конвертация в MP3: {input_path} -> {output_path}")
            
            # Получаем метаданные из исходного файла для сохранения
            metadata = self._get_metadata(input_path)
            
            # Явно передаем все метаданные, НЕ используя -map_metadata
            metadata_params = []
            for key, value in metadata.items():
                if value:  # Пропускаем пустые значения
                    # Экранируем значения метаданных
                    value_str = str(value).replace('\\', '\\\\').replace(':', '\\:').replace('=', '\\=')
                    metadata_params.extend(['-metadata', f'{key}={value_str}'])
            
            # Собираем команду ffmpeg для конвертации в MP3
            cmd = [
                'ffmpeg',
                '-i', str(input_path),
                '-map_metadata', '-1',  # НЕ копируем метаданные автоматически
                *metadata_params,  # Добавляем только явно указанные метаданные
                '-acodec', 'libmp3lame',
                '-q:a', '2',  # Качество ~192 kbps
                '-id3v2_version', '3',
                '-write_id3v2', '1',
                '-y',
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                logger.error(f"Ошибка при конвертации в MP3: {result.stderr}")
                return False
            
            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error("MP3 файл не создан или пуст")
                return False
            
            logger.info(f"Файл успешно сконвертирован в MP3: {output_path}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Превышено время конвертации в MP3 (5 минут)")
            return False
        except Exception as e:
            logger.error(f"Ошибка при конвертации в MP3: {e}", exc_info=True)
            return False
    
    def is_telegram_playable_format(self, file_path: Path) -> bool:
        """
        Проверяет, может ли Telegram воспроизвести файл напрямую
        
        Args:
            file_path: Путь к файлу
        
        Returns:
            True если формат поддерживается для прямого воспроизведения
        """
        extension = file_path.suffix.lower()
        # Telegram поддерживает для прямого воспроизведения: MP3, OGG, M4A
        playable_formats = {'.mp3', '.ogg', '.m4a', '.aac'}
        return extension in playable_formats

