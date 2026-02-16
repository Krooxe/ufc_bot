"""
Fight Service - управление боями
"""
import logging
from typing import List, Optional, Dict
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import Fight

logger = logging.getLogger(__name__)


async def get_fights_for_event(session: AsyncSession, event_id: int) -> List[Fight]:
    """Получает все бои для турнира"""
    result = await session.execute(
        select(Fight)
        .where(Fight.event_id == event_id)
        .order_by(Fight.fight_order)
    )
    return list(result.scalars().all())


async def update_fight_odds(
    session: AsyncSession,
    fight_id: int,
    odds1: float,
    odds2: float
) -> bool:
    """Обновляет коэффициенты боя"""
    try:
        result = await session.execute(
            select(Fight).where(Fight.id == fight_id)
        )
        fight = result.scalar_one_or_none()
        
        if fight:
            fight.odds1 = Decimal(str(odds1))
            fight.odds2 = Decimal(str(odds2))
            await session.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка update_fight_odds: {e}")
        await session.rollback()
        return False


async def update_fight_odds_batch(
    session: AsyncSession,
    event_id: int,
    odds_list: List[Dict]
) -> int:
    """Массовое обновление коэффициентов"""
    try:
        fights = await get_fights_for_event(session, event_id)
        updated = 0
        
        for odds_data in odds_list:
            fight_order = odds_data.get('fight_order')
            odds1 = odds_data.get('odds1')
            odds2 = odds_data.get('odds2')
            
            for fight in fights:
                if fight.fight_order == fight_order:
                    fight.odds1 = Decimal(str(odds1))
                    fight.odds2 = Decimal(str(odds2))
                    updated += 1
                    break
        
        await session.commit()
        return updated
    except Exception as e:
        logger.error(f"Ошибка update_fight_odds_batch: {e}")
        await session.rollback()
        return 0


async def update_fights_with_results(
    session: AsyncSession,
    event_id: int,
    results: List[Dict]
) -> bool:
    """Обновляет результаты боёв"""
    try:
        fights = await get_fights_for_event(session, event_id)
        
        for result in results:
            fight_order = result.get('fight_order')
            winner = result.get('winner')
            
            for fight in fights:
                if fight.fight_order == fight_order:
                    fight.winner = winner
                    break
        
        await session.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка update_fights_with_results: {e}")
        await session.rollback()
        return False
