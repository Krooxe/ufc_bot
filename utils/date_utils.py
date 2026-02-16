import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

def parse_iso_date(date_string: str) -> datetime:
    """
    Парсит дату из ISO формата (совместимость с ufcstats и ESPN)
    СИНХРОННАЯ функция - не делает асинхронных операций
    """
    try:
        if not date_string:
            return datetime.now(timezone.utc)
            
        # Формат ISO с Z (UTC) или со смещением
        if 'Z' in date_string:
            date_string = date_string.replace('Z', '+00:00')
        
        dt = datetime.fromisoformat(date_string)
        # Убеждаемся что дата с таймзоной
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.error(f"Ошибка парсинга даты '{date_string}': {e}")
        return datetime.now(timezone.utc)