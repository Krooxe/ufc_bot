"""
User Service - управление пользователями
"""
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import User

logger = logging.getLogger(__name__)


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
        return user
    else:
        # ОБНОВЛЯЕМ данные пользователя, если они изменились
        updated = False
        if username and user.username != username:
            user.username = username
            updated = True
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        
        if updated:
            await session.commit()
            logger.info(f"Обновлены данные пользователя: {user_id}")
        
        return user


async def get_all_users(session: AsyncSession) -> List[User]:
    """Получает всех пользователей"""
    result = await session.execute(
        select(User).order_by(User.created_at.desc())
    )
    return result.scalars().all()


async def get_user_balance(session: AsyncSession, user_id: int) -> float:
    """Получает баланс пользователя"""
    result = await session.execute(
        select(User.total_balance).where(User.user_id == user_id)
    )
    balance = result.scalar_one_or_none()
    return float(balance) if balance else 0.0


async def update_user_balance(
    session: AsyncSession,
    user_id: int,
    amount: float
) -> bool:
    """Обновляет баланс пользователя"""
    try:
        result = await session.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            current = float(user.total_balance or 0)
            user.total_balance = current + amount
            await session.commit()
            logger.info(f"Баланс пользователя {user_id} изменён на {amount}")
            return True
        return False
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка обновления баланса: {e}")
        return False