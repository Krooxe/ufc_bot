import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from database import User, Event, Fight, Bet, Setting, engine  # УБИРАЕМ async_session, добавляем engine
import config

# Функция для создания сессии
def get_session() -> AsyncSession:
    """Создаёт новую сессию"""
    return AsyncSession(engine, expire_on_commit=False)

# Остальной код...

logger = logging.getLogger(__name__)
