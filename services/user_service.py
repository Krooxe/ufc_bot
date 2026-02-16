"""
User Service - управление пользователями
"""
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import User

logger = logging.getLogger(__name__)
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка создания турнира: {e}")
        return None

async def get_event_by_title(session: AsyncSession, title: str) -> Optional[Event]:
    """Ищет турнир по названию"""
    result = await session.execute(
        select(Event).where(Event.title == title)
    )
    return result.scalar_one_or_none()

async def get_current_event(session: AsyncSession) -> Optional[Event]:
    """
    Возвращает текущий активный турнир (статус 'draft' или 'open_for_bets')
    """
    result = await session.execute(
        select(Event)
        .where(Event.status.in_(['draft', 'open_for_bets']))
        .order_by(Event.date_utc.asc())
    )
    return result.scalar_one_or_none()

# ==================== УТИЛИТЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ====================

async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str = None,
    full_name: str = None
) -> User:
    """Получает или создает пользователя, обновляет данные если изменились"""
    result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        # Создаем нового пользователя
        user = User(
            user_id=user_id,
            username=username,
            full_name=full_name
        )
        session.add(user)
        await session.commit()
        logger.info(f"Создан новый пользователь: {user_id}")
    else:
        # ОБНОВЛЯЕМ данные пользователя, если они изменились
        updated = False
        if username and user.username != username:
# ==================== УТИЛИТЫ ДЛЯ НАСТРОЕК ====================

async def get_setting(session: AsyncSession, key: str) -> Optional[str]:
    """Получает значение настройки"""
    result = await session.execute(
        select(Setting.value).where(Setting.key == key)
    )
    return result.scalar_one_or_none()

async def set_setting(session: AsyncSession, key: str, value: str) -> None:
