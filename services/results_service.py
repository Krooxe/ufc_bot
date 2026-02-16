"""
Results Service - обработка результатов и расчёт очков
"""
import logging
from typing import Optional, Dict, List
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import Event, Fight, Bet, User

logger = logging.getLogger(__name__)


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
        
        if not bets:
            return 0.0
        
        # Разделяем ставки на основные и страховочные
        main_bets = [b for b in bets if b.bet_type == 'main']
        insurance_bet = next((b for b in bets if b.bet_type == 'insurance'), None)
        
        # Собираем информацию о боях
        fights_dict = {}
        for bet in bets:
            fight = await session.get(Fight, bet.fight_id)
            if fight:
                fights_dict[bet.fight_id] = fight
        
        # Проверяем, нужна ли страховка
        insurance_needed = False
        problematic_fights = []
        
        if insurance_bet:
            for main_bet in main_bets:
                fight = fights_dict.get(main_bet.fight_id)
                if fight:
                    # Проверяем проблемные исходы
                    if fight.winner in ['draw', 'nc', 'cancelled']:
                        insurance_needed = True
                        problematic_fights.append({
                            'fight': fight,
                            'bet': main_bet
                        })
        
        total_points = 0.0
        
        # Обрабатываем основные ставки
        for bet in main_bets:
            fight = fights_dict.get(bet.fight_id)
            
            if not fight or not fight.winner:
                # Бой без результата - пропускаем
                bet.status = 'pending'
                continue
            
            # Проверяем результат
            if fight.winner in ['draw', 'nc', 'cancelled']:
                # Бой с проблемным исходом
                bet.status = 'cancelled'
                bet.points_earned = Decimal('0.0')
                continue
            
            # Проверяем, угадал ли пользователь
            if str(bet.chosen_fighter) == str(fight.winner):
                # Угадал!
                if bet.chosen_fighter == 1 and fight.odds1:
                    points = float(fight.odds1)
                elif bet.chosen_fighter == 2 and fight.odds2:
                    points = float(fight.odds2)
                else:
                    points = 1.0
                
                total_points += points
                bet.status = 'win'
                bet.points_earned = Decimal(str(points))
            else:
                # Не угадал
                total_points -= 1.0
                bet.status = 'lose'
                bet.points_earned = Decimal('0.0')
        
        # Обрабатываем страховочную ставку (только если нужна)
        if insurance_bet and insurance_needed:
            fight = fights_dict.get(insurance_bet.fight_id)
            
            if fight and fight.winner:
                # Проверяем, что страховочный бой не проблемный
                if fight.winner not in ['draw', 'nc', 'cancelled']:
                    # Страховочный бой прошёл штатно - считаем очки
                    if str(insurance_bet.chosen_fighter) == str(fight.winner):
                        # Угадал на страховке
                        if insurance_bet.chosen_fighter == 1 and fight.odds1:
                            points = float(fight.odds1)
                        elif insurance_bet.chosen_fighter == 2 and fight.odds2:
                            points = float(fight.odds2)
                        else:
                            points = 1.0
                        
                        total_points += points
                        insurance_bet.status = 'win'
                        insurance_bet.points_earned = Decimal(str(points))
                        
                        logger.info(f"✅ Страховка сработала! Игрок {user_id} получил {points} очков")
                    else:
                        # Не угадал на страховке
                        insurance_bet.status = 'lose'
                        insurance_bet.points_earned = Decimal('0.0')
                else:
                    # Страховочный бой тоже проблемный
                    insurance_bet.status = 'cancelled'
                    insurance_bet.points_earned = Decimal('0.0')
            else:
                insurance_bet.status = 'pending'
        elif insurance_bet:
            # Страховка не нужна - помечаем как неиспользованную
            insurance_bet.status = 'not_used'
            insurance_bet.points_earned = Decimal('0.0')
            logger.info(f"ℹ️ Страховка не использована: все основные бои прошли штатно")
        
        # Сохраняем изменения
        await session.commit()
        
        return total_points
        
    except Exception as e:
        logger.error(f"Ошибка calculate_user_points_for_event: {e}", exc_info=True)
        await session.rollback()
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
        
        if not users:
            return {
                'total_bets': 0,
                'updated': 0
            }
        
        updated = 0
        total_bets_count = 0
        
        for user in users:
            # Получаем количество ставок пользователя
            bets_result = await session.execute(
                select(Bet)
                .join(Fight)
                .where(
                    Bet.user_id == user.user_id,
                    Fight.event_id == event_id
                )
            )
            user_bets = bets_result.scalars().all()
            total_bets_count += len(user_bets)
            
            # Рассчитываем очки за турнир
            points = await calculate_user_points_for_event(
                session, user.user_id, event_id
            )
            
            # Обновляем общий баланс
            current_balance = float(user.total_balance or 0)
            user.total_balance = current_balance + points
            updated += 1
            
            logger.info(f"Игрок {user.user_id} заработал {points} очков за турнир")
        
        await session.commit()
        
        return {
            'total_bets': total_bets_count,
            'updated': updated
        }
        
    except Exception as e:
        logger.error(f"Ошибка calculate_points_for_event: {e}", exc_info=True)
        await session.rollback()
        return None