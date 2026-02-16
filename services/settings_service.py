"""
Settings Service - настройки приложения
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import Setting

logger = logging.getLogger(__name__)
    """Получает баланс пользователя"""
    result = await session.execute(
        select(User.total_balance).where(User.user_id == user_id)
    )
    balance = result.scalar_one_or_none()
    return float(balance) if balance else 0.0
