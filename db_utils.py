import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from database import User, Event, Fight, Bet, Setting, async_session
import config

logger = logging.getLogger(__name__)

# ==================== ФУНКЦИИ ОТЛАДКИ ====================

async def debug_event_creation(session: AsyncSession, event_data: Dict, fights_data: List[Dict]):
    """Функция для отладки создания турнира"""
    try:
        logger.info("=" * 50)
        logger.info("ОТЛАДКА СОЗДАНИЯ ТУРНИРА")
        logger.info(f"Данные события: {event_data.get('name')}")
        logger.info(f"ID события: {event_data.get('id')}")
        logger.info(f"Дата: {event_data.get('date')}")
        logger.info(f"Количество боев: {len(fights_data)}")
        
        # Парсим дату
        from ufc_api import parse_espn_date
        event_date_utc = parse_espn_date(event_data.get('date', ''))
        logger.info(f"Парсинг даты: {event_date_utc}")
        
        # Проверяем год
        year = event_date_utc.year
        logger.info(f"Год: {year}")
        
        # Проверяем статус
        current_time = datetime.now(timezone.utc)
        logger.info(f"Текущее время: {current_time}")
        logger.info(f"Время события: {event_date_utc}")
        status = "draft" if event_date_utc > current_time else "finished"
        logger.info(f"Статус: {status}")
        
        # Обрабатываем ID
        api_id = event_data.get('id')
        logger.info(f"API ID: {api_id}, тип: {type(api_id)}")
        
        if api_id and str(api_id).isdigit():
            ufc_api_id = int(api_id)
        else:
            ufc_api_id = None
        logger.info(f"UFC API ID: {ufc_api_id}")
        
        # Показываем первых 3 боя
        for i, fight in enumerate(fights_data[:3], 1):
            logger.info(f"Бой {i}: {fight.get('fighter1', {}).get('name')} vs {fight.get('fighter2', {}).get('name')}")
        
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"Ошибка в отладке: {e}")

# ==================== УТИЛИТЫ ДЛЯ СОБЫТИЙ ====================

async def create_event_from_api(
    session: AsyncSession,
    event_data: Dict,
    fights_data: List[Dict]
) -> Optional[Event]:
    """
    Создает турнир в базе данных на основе данных из API
    """
    try:
        # Добавляем отладку
        await debug_event_creation(session, event_data, fights_data)
        
        # Парсим дату из API
        from ufc_api import parse_espn_date
        event_date_utc = parse_espn_date(event_data.get('date', ''))
        
        # Определяем год
        year = event_date_utc.year
        
        # Определяем статус
        current_time = datetime.now(timezone.utc)
        status = "draft" if event_date_utc > current_time else "finished"
        
        # Обрабатываем ID (может быть строкой для тестовых данных)
        api_id = event_data.get('id')
        if api_id and str(api_id).isdigit():
            ufc_api_id = int(api_id)
        else:
            ufc_api_id = None
        
        # Создаем событие
        event = Event(
            ufc_api_id=ufc_api_id,
            title=event_data.get('name', 'Без названия'),
            short_title=event_data.get('shortName', 'UFC ?'),
            year=year,
            date_utc=event_date_utc,
            date_msk=event_date_utc,  # Пока то же время
            status=status
        )
        
        session.add(event)
        await session.flush()
        
        # Создаем бои
        for i, fight_data in enumerate(fights_data, 1):
            fight = Fight(
                event_id=event.id,
                fight_order=i,
                fighter1_name=fight_data.get('fighter1', {}).get('name', 'Боец 1'),
                fighter2_name=fight_data.get('fighter2', {}).get('name', 'Боец 2'),
                odds1=None,
                odds2=None,
                winner=None
            )
            session.add(fight)
        
        await session.commit()
        logger.info(f"Создан турнир: {event.title} (ID: {event.id}) с {len(fights_data)} боями")
        return event
        
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
            user.username = username
            updated = True
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        
        if updated:
            await session.commit()
            logger.info(f"Обновлены данные пользователя: {user_id}")
    
    return user

async def get_user_bets_for_event(
    session: AsyncSession,
    user_id: int,
    event_id: int
) -> List[Bet]:
    """Получает все ставки пользователя на турнир"""
    result = await session.execute(
        select(Bet)
        .where(
            and_(
                Bet.user_id == user_id,
                Bet.event_id == event_id
            )
        )
        .order_by(Bet.bet_type.desc())  # Сначала основные, потом страховочные
    )
    return result.scalars().all()

async def get_user_balance(session: AsyncSession, user_id: int) -> float:
    """Получает баланс пользователя"""
    result = await session.execute(
        select(User.total_balance).where(User.user_id == user_id)
    )
    balance = result.scalar_one_or_none()
    return float(balance) if balance else 0.0

# ==================== УТИЛИТЫ ДЛЯ НАСТРОЕК ====================

async def get_setting(session: AsyncSession, key: str) -> Optional[str]:
    """Получает значение настройки"""
    result = await session.execute(
        select(Setting.value).where(Setting.key == key)
    )
    return result.scalar_one_or_none()

async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    """Устанавливает значение настройки"""
    setting = await session.execute(
        select(Setting).where(Setting.key == key)
    )
    setting = setting.scalar_one_or_none()
    
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        session.add(setting)
    
    await session.commit()


# ==================== УТИЛИТЫ ДЛЯ КОЭФФИЦИЕНТОВ ====================

async def get_fights_for_event(session: AsyncSession, event_id: int) -> List[Fight]:
    """Получает все бои турнира"""
    result = await session.execute(
        select(Fight)
        .where(Fight.event_id == event_id)
        .order_by(Fight.fight_order.asc())
    )
    return result.scalars().all()

async def update_fight_odds(
    session: AsyncSession, 
    fight_id: int, 
    odds1: float, 
    odds2: float
) -> bool:
    """Обновляет коэффициенты для боя"""
    try:
        result = await session.execute(
            select(Fight).where(Fight.id == fight_id)
        )
        fight = result.scalar_one_or_none()
        
        if fight:
            fight.odds1 = odds1
            fight.odds2 = odds2
            await session.commit()
            logger.info(f"Обновлены коэффициенты для боя {fight_id}: {odds1}/{odds2}")
            return True
        return False
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка обновления коэффициентов: {e}")
        return False

async def get_event_by_id(session: AsyncSession, event_id: int) -> Optional[Event]:
    """Получает турнир по ID"""
    result = await session.execute(
        select(Event).where(Event.id == event_id)
    )
    return result.scalar_one_or_none()

async def open_event_for_bets(session: AsyncSession, event_id: int) -> bool:
    """Открывает турнир для ставок"""
    try:
        result = await session.execute(
            select(Event).where(Event.id == event_id)
        )
        event = result.scalar_one_or_none()
        
        if event and event.status == 'draft':
            event.status = 'open_for_bets'
            await session.commit()
            logger.info(f"Турнир {event_id} открыт для ставок")
            return True
        return False
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка открытия турнира: {e}")
        return False

async def get_draft_events(session: AsyncSession) -> List[Event]:
    """
    Возвращает список турниров в статусе 'draft'
    (для выбора админом)
    """
    result = await session.execute(
        select(Event)
        .where(Event.status == 'draft')
        .order_by(Event.date_utc.asc())
    )
    return result.scalars().all()

async def get_open_event(session: AsyncSession) -> Optional[Event]:
    """
    Возвращает турнир открытый для ставок (status='open_for_bets')
    Только один может быть активным!
    """
    result = await session.execute(
        select(Event)
        .where(Event.status == 'open_for_bets')
        .order_by(Event.date_utc.asc())
    )
    return result.scalar_one_or_none()

async def update_fight_odds_batch(
    session: AsyncSession,
    event_id: int,
    odds_list: List[tuple]  # Список кортежей (fight_id, odds1, odds2)
) -> bool:
    """
    Обновляет коэффициенты для нескольких боев сразу
    odds_list: [(fight_id1, odds1_1, odds1_2), (fight_id2, odds2_1, odds2_2), ...]
    """
    try:
        for fight_id, odds1, odds2 in odds_list:
            result = await session.execute(
                select(Fight).where(Fight.id == fight_id)
            )
            fight = result.scalar_one_or_none()
            
            if fight:
                fight.odds1 = odds1
                fight.odds2 = odds2
            else:
                logger.error(f"Бой {fight_id} не найден")
                return False
        
        await session.commit()
        logger.info(f"Обновлены коэффициенты для {len(odds_list)} боев турнира {event_id}")
        return True
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка пакетного обновления коэффициентов: {e}")
        return False

async def get_open_event_with_fights(session: AsyncSession) -> Optional[Dict]:
    """
    Возвращает открытый турнир со списком боев и коэффициентами
    """
    try:
        event = await get_open_event(session)
        logger.info(f"get_open_event вернул: {event}")
        
        if not event:
            logger.info("Нет открытого турнира")
            return None
        
        fights = await get_fights_for_event(session, event.id)
        logger.info(f"Получено боев: {len(fights)}")
        
        return {
            'event': event,
            'fights': fights
        }
        
    except Exception as e:
        logger.error(f"Ошибка в get_open_event_with_fights: {e}")
        return None

async def get_open_or_draft_events(session: AsyncSession) -> List[Event]:
    """Получает турниры для редактирования коэффициентов"""
    result = await session.execute(
        select(Event)
        .where(Event.status.in_(['draft', 'open_for_bets']))
        .order_by(Event.date_utc.asc())
    )
    return result.scalars().all()

async def save_user_bets(
    session: AsyncSession,
    user_id: int,
    event_id: int,
    bets_data: dict,
    username: str = None,  # ДОБАВИТЬ
    full_name: str = None  # ДОБАВИТЬ
) -> bool:
    
    try:
        # Проверяем, что пользователь существует
        user = await get_or_create_user(
            session, user_id, username, full_name
        )
        
        # Удаляем старые ставки пользователя на этот турнир (если есть)
        # ПРАВИЛЬНЫЙ СИНТАКСИС ДЛЯ SQLAlchemy 2.0
        from sqlalchemy import delete
        
        await session.execute(
            delete(Bet).where(
                and_(
                    Bet.user_id == user_id,
                    Bet.event_id == event_id
                )
            )
        )
        
        # Сохраняем основные ставки (5 штук)
        for bet_data in bets_data['main_bets']:
            bet = Bet(
                user_id=user_id,
                event_id=event_id,
                fight_id=bet_data['fight_id'],
                bet_type='main',
                chosen_fighter=bet_data['chosen_fighter'],
                odds_at_bet=bet_data['odds'],
                status='pending',
                points_earned=0.0
            )
            session.add(bet)
        
        # Сохраняем страховочную ставку (если есть)
        if bets_data.get('insurance_bet'):
            ins_bet = bets_data['insurance_bet']
            bet = Bet(
                user_id=user_id,
                event_id=event_id,
                fight_id=ins_bet['fight_id'],
                bet_type='insurance',
                chosen_fighter=ins_bet['chosen_fighter'],
                odds_at_bet=ins_bet['odds'],
                status='pending',
                points_earned=0.0
            )
            session.add(bet)
        
        await session.commit()
        logger.info(f"Сохранены ставки для user_id={user_id} на event_id={event_id}")
        return True
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка сохранения ставок: {e}", exc_info=True)  # Добавим traceback
        return False

async def get_events_for_odds_edit(session: AsyncSession) -> List[Event]:
    """
    Получает турниры для редактирования коэффициентов
    (и черновики, и открытые для ставок)
    """
    result = await session.execute(
        select(Event)
        .where(Event.status.in_(['draft', 'open_for_bets']))
        .order_by(Event.date_utc.asc())
    )
    return result.scalars().all()

async def update_event_results_from_api(session: AsyncSession, event: Event) -> bool:
    """
    Обновляет результаты турнира из API
    """
    try:
        # ДЛЯ ТЕСТОВОГО РЕЖИМА: если DEBUG_MODE = True, всегда обновляем
        if config.DEBUG_MODE:
            logger.info(f"DEBUG_MODE: обновляем результаты для турнира {event.id}")
            from ufc_api import get_test_results
            
            results = get_test_results()
            
            # Получаем существующие бои турнира
            fights = await get_fights_for_event(session, event.id)
            fights_dict = {f.fight_order: f for f in fights}
            
            # Обновляем результаты
            updated_count = 0
            for result in results:
                fight_order = result.get('fight_order')
                if not fight_order:
                    continue
                    
                # Находим соответствующий бой
                fight = fights_dict.get(fight_order)
                if fight and fight.winner is None:  # Обновляем только если еще нет результата
                    # Обновляем результат
                    fight.winner = result.get('winner')
                    updated_count += 1
            
            # Помечаем турнир как завершенный если все бои имеют результаты
            if updated_count > 0:
                await mark_event_as_finished(session, event.id)
                await session.commit()
                logger.info(f"DEBUG_MODE: обновлены результаты для {updated_count} боев турнира {event.id}")
                return True
            else:
                logger.warning(f"DEBUG_MODE: не найдено боев для обновления в турнире {event.id}")
                return False
        
        # РЕАЛЬНЫЙ API (если DEBUG_MODE = False)
        if not event.ufc_api_id:
            logger.warning(f"У турнира {event.id} нет API ID, нельзя обновить результаты")
            return False
        
        # Получаем результаты из API
        from ufc_api import fetch_event_results
        results = await fetch_event_results(str(event.ufc_api_id))
        
        if not results:
            logger.warning(f"Не удалось получить результаты для турнира {event.id}")
            return False
        
        # Получаем существующие бои турнира
        fights = await get_fights_for_event(session, event.id)
        fights_dict = {f.fight_order: f for f in fights}
        
        # Обновляем результаты
        updated_count = 0
        for result in results:
            fight_order = result.get('fight_order')
            if not fight_order:
                continue
                
            # Находим соответствующий бой
            fight = fights_dict.get(fight_order)
            if fight and fight.winner is None:  # Обновляем только если еще нет результата
                # Обновляем результат
                fight.winner = result.get('winner')
                fight.odds1 = result.get('odds1', fight.odds1)  # Сохраняем старые коэфы если новых нет
                fight.odds2 = result.get('odds2', fight.odds2)
                updated_count += 1
        
        # Помечаем турнир как завершенный если все бои имеют результаты
        if updated_count > 0:
            await mark_event_as_finished(session, event.id)
            await session.commit()
            logger.info(f"Обновлены результаты для {updated_count} боев турнира {event.id}")
            return True
        else:
            logger.warning(f"Не найдено боев для обновления в турнире {event.id}")
            return False
            
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка обновления результатов: {e}", exc_info=True)
        return False

async def get_finished_events(session: AsyncSession) -> List[Event]:
    """Получает завершенные турниры"""
    result = await session.execute(
        select(Event)
        .where(Event.status == 'finished')
        .order_by(Event.date_utc.desc())
    )
    return result.scalars().all()

async def get_events_needing_results(session: AsyncSession) -> List[Event]:
    """
    Получает турниры, которые нуждаются в обновлении результатов
    (прошли по времени, но еще не имеют статус 'finished')
    """
    from datetime import datetime, timezone
    
    current_time = datetime.now(timezone.utc)
    
    result = await session.execute(
        select(Event).where(
            Event.status.in_(['open_for_bets', 'draft']),
            Event.date_utc < current_time
        ).order_by(Event.date_utc.desc())
    )
    return result.scalars().all()

async def calculate_user_points_for_event(session: AsyncSession, user_id: int, event_id: int) -> float:
    """
    Рассчитывает очки пользователя за турнир
    """
    try:
        logger.info(f"РАСЧЕТ ОЧКОВ: user_id={user_id}, event_id={event_id}")
        
        # Получаем все ставки пользователя на этот турнир
        bets = await get_user_bets_for_event(session, user_id, event_id)
        logger.info(f"Найдено ставок: {len(bets)}")
        
        if not bets:
            return 0.0
        
        # Получаем все бои турнира
        fights = await get_fights_for_event(session, event_id)
        fights_dict = {f.id: f for f in fights}
        logger.info(f"Найдено боев: {len(fights)}")
        
        total_points = 0.0
        used_insurance = False
        
        # Разделяем ставки
        main_bets = [b for b in bets if b.bet_type == 'main']
        insurance_bet = next((b for b in bets if b.bet_type == 'insurance'), None)
        
        logger.info(f"Основных ставок: {len(main_bets)}, Страховочная: {'есть' if insurance_bet else 'нет'}")
        
        # Проверяем основные ставки
        cancelled_fights = []
        
        for bet in main_bets:
            fight = fights_dict.get(bet.fight_id)
            if not fight:
                logger.warning(f"Бой {bet.fight_id} не найден для ставки {bet.id}")
                continue
            
            logger.info(f"Проверка ставки {bet.id}: бой {fight.fight_order}, победитель={fight.winner}, выбрал={bet.chosen_fighter}")
            
            # Проверяем результат боя
            if fight.winner == str(bet.chosen_fighter):
                # Угадал победителя
                points = float(bet.odds_at_bet) if bet.odds_at_bet else 0.0
                total_points += points
                
                # Обновляем статус ставки - КОРРЕКТНЫЙ ТИП ДАННЫХ
                bet.status = 'win'
                bet.points_earned = float(points)  # Важно: приводим к float
                logger.info(f"✅ ВЫИГРЫШ: +{points} очков")
                
            elif fight.winner in ['draw', 'nc', 'cancelled', None]:
                # Бой не состоялся или нет результата
                cancelled_fights.append(bet.fight_id)
                bet.status = 'cancelled'
                bet.points_earned = 0.0  # float вместо Decimal
                logger.info(f"➖ ОТМЕНА: бой {fight.fight_order} - {fight.winner}")
                
            else:
                # Не угадал
                bet.status = 'lose'
                bet.points_earned = 0.0  # float вместо Decimal
                logger.info(f"❌ ПРОИГРЫШ")
        
        # Если есть отмененные бои и есть страховочная ставка
        if cancelled_fights and insurance_bet and not used_insurance:
            logger.info(f"Проверяем страховку для отмененных боев: {cancelled_fights}")
            
            fight = fights_dict.get(insurance_bet.fight_id)
            if fight and fight.winner == str(insurance_bet.chosen_fighter):
                points = float(insurance_bet.odds_at_bet) if insurance_bet.odds_at_bet else 0.0
                total_points += points
                insurance_bet.status = 'win'
                insurance_bet.points_earned = float(points)  # float вместо Decimal
                used_insurance = True
                logger.info(f"🛡️ СТРАХОВКА СЫГРАЛА: +{points} очков")
            else:
                insurance_bet.status = 'lose'
                insurance_bet.points_earned = 0.0  # float вместо Decimal
                logger.info(f"🛡️ СТРАХОВКА НЕ СЫГРАЛА")
        
        logger.info(f"ИТОГО ОЧКОВ: {total_points}")
        await session.commit()
        return total_points
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка расчета очков: {e}", exc_info=True)
        return 0.0

async def is_event_finished(session: AsyncSession, event_id: int) -> bool:
    """
    Проверяет, завершен ли турнир
    Критерии: все бои имеют результат (winner не None и не пустая строка)
    """
    try:
        fights = await get_fights_for_event(session, event_id)
        
        if not fights:
            return False  # Нет боев - не завершен
        
        # Проверяем, есть ли бои без результата
        for fight in fights:
            # ⚠️ ИСПРАВЛЕНО: проверяем не только None, но и пустую строку
            if fight.winner is None or fight.winner == '':
                return False  # Нашли бой без результата
        
        return True  # Все бои имеют результат
        
    except Exception as e:
        logger.error(f"Ошибка проверки завершенности турнира: {e}")
        return False

async def mark_event_as_finished(session: AsyncSession, event_id: int) -> bool:
    """
    Помечает турнир как завершенный (форсированно)
    """
    try:
        event = await get_event_by_id(session, event_id)
        if event and event.status != 'finished':
            event.status = 'finished'
            await session.commit()
            logger.info(f"Турнир {event_id} помечен как завершенный")
            return True
        elif event and event.status == 'finished':
            # Турнир уже завершен, возвращаем True
            logger.info(f"Турнир {event_id} уже завершен")
            return True
        return False
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка пометки турнира как завершенного: {e}")
        return False
    
async def get_unfinished_events(session: AsyncSession) -> List[Event]:
    """
    Получает незавершенные турниры (есть хотя бы один бой без результата)
    """
    # Получаем все турниры не в статусе 'finished'
    result = await session.execute(
        select(Event)
        .where(Event.status != 'finished')
        .order_by(Event.date_utc.desc())
    )
    events = result.scalars().all()
    
    # Фильтруем те, у которых действительно есть незавершенные бои
    unfinished_events = []
    for event in events:
        fights = await get_fights_for_event(session, event.id)
        if fights:
            # Проверяем, есть ли бои без результата
            has_unfinished_fights = any(fight.winner is None for fight in fights)
            if has_unfinished_fights:
                unfinished_events.append(event)
    
    return unfinished_events
    
if __name__ == "__main__":
    # Тест утилит
    import asyncio
    
    async def test():
        async with async_session() as session:
            # Создаем тестового пользователя
            user = await get_or_create_user(
                session, 
                user_id=123456,
                username="test_user",
                full_name="Test User"
            )
            print(f"Пользователь: {user.user_id}, баланс: {user.total_balance}")
            
            # Получаем текущий турнир
            event = await get_current_event(session)
            if event:
                print(f"Текущий турнир: {event.title}")
            else:
                print("Активных турниров нет")
    
    asyncio.run(test())