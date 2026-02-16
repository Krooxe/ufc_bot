"""
Results Service - обработка результатов и расчёт очков
"""
import logging
from typing import Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import Event, Fight, Bet, User

logger = logging.getLogger(__name__)


async def update_event_results_from_api(
    session: AsyncSession,
    event: Event
) -> bool:
    """Обновляет результаты турнира из API"""
    try:
        # TODO: Реализовать получение результатов из API
        # Пока заглушка
        logger.warning("update_event_results_from_api: не реализовано")
        return False
    except Exception as e:
        logger.error(f"Ошибка update_event_results_from_api: {e}")
        return False


async def calculate_user_points_for_event(
    session: AsyncSession,
    user_id: int,
    event_id: int
) -> float:
    """Рассчитывает очки пользователя за турнир"""
    try:
        # Получаем ставки пользователя
        result = await session.execute(
            select(Bet)
            .join(Fight)
            .where(
                Bet.user_id == user_id,
                Fight.event_id == event_id
            )
        )
        bets = result.scalars().all()
        
        total_points = 0.0
        
        for bet in bets:
            # Получаем бой
            fight = await session.get(Fight, bet.fight_id)
            
            if fight and fight.winner:
                # Проверяем угадал ли
                if bet.predicted_winner == fight.winner:
                    # Угадал!
                    if bet.predicted_winner == '1' and fight.odds1:
                        points = float(fight.odds1)
                    elif bet.predicted_winner == '2' and fight.odds2:
                        points = float(fight.odds2)
                    else:
                        points = 1.0
                    
                    total_points += points
                else:
                    # Не угадал
                    if bet.insurance_used:
                        # Страховка - не теряем очки
                        pass
                    else:
                        # Теряем 1 очко
                        total_points -= 1.0
        
        # Обновляем очки пользователя
        bet_result = await session.execute(
            select(Bet)
            .join(Fight)
            .where(
                Bet.user_id == user_id,
                Fight.event_id == event_id
            )
        )
        user_bets = bet_result.scalars().all()
        
        for bet in user_bets:
            bet.points_earned = total_points / len(user_bets) if user_bets else 0
        
        await session.commit()
        return total_points
        
    except Exception as e:
        logger.error(f"Ошибка calculate_user_points_for_event: {e}")
        return 0.0


async def calculate_points_for_event(
    session: AsyncSession,
    event_id: int
) -> Optional[Dict]:
    """Рассчитывает очки для всех пользователей турнира"""
    try:
        # Получаем всех пользователей со ставками
        result = await session.execute(
            select(User)
            .join(Bet)
            .join(Fight)
            .where(Fight.event_id == event_id)
            .distinct()
        )
        users = result.scalars().all()
        
        updated = 0
        for user in users:
            points = await calculate_user_points_for_event(
                session, user.user_id, event_id
            )
            
            # Обновляем баланс
            user.balance = float(user.balance or 0) + points
            updated += 1
        
        await session.commit()
        
        return {
            'total_bets': updated,
            'updated': updated
        }
        
    except Exception as e:
        logger.error(f"Ошибка calculate_points_for_event: {e}")
        await session.rollback()
        return None
