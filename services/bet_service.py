"""
Bet Service - управление ставками
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from database import Bet, Fight, User

logger = logging.getLogger(__name__)


async def get_user_bets_for_event(
    session: AsyncSession,
    user_id: int,
    event_id: int
) -> List[Bet]:
    """Получает ставки пользователя на турнир"""
    result = await session.execute(
        select(Bet)
        .join(Fight)
        .where(
            and_(
                Bet.user_id == user_id,
                Fight.event_id == event_id
            )
        )
    )
    return list(result.scalars().all())


async def save_user_bets(
    session: AsyncSession,
    user_id: int,
    event_id: int,
    bets_data: List[Dict]
) -> bool:
    """Сохраняет ставки пользователя"""
    try:
        # Удаляем старые ставки
        old_bets = await get_user_bets_for_event(session, user_id, event_id)
        for bet in old_bets:
            await session.delete(bet)
        
        # Создаём новые
        for bet_data in bets_data:
            bet = Bet(
                user_id=user_id,
                fight_id=bet_data['fight_id'],
                predicted_winner=bet_data['predicted_winner'],
                insurance_used=bet_data.get('insurance_used', False)
            )
            session.add(bet)
        
        await session.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка save_user_bets: {e}")
        await session.rollback()
        return False
