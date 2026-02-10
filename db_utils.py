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

def parse_iso_date(date_string: str) -> datetime:
    """
    Парсит дату из ISO формата (совместимость с ufcstats и ESPN)
    СИНХРОННАЯ функция - не делает асинхронных операций
    """
    try:
        # Формат ISO с Z (UTC) или со смещением
        if 'Z' in date_string:
            date_string = date_string.replace('Z', '+00:00')
        
        dt = datetime.fromisoformat(date_string)
        return dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.error(f"Ошибка парсинга даты '{date_string}': {e}")
        return datetime.now(timezone.utc)

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
        event_date_utc = parse_iso_date(event_data.get('date', ''))
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
        event_date_utc = parse_iso_date(event_data.get('date', ''))
        
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

async def get_all_users(session: AsyncSession) -> List[User]:
    """Получает всех пользователей"""
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()

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
    username: str = None,
    full_name: str = None
) -> bool:
    try:
        # Проверяем, что пользователь существует
        user = await get_or_create_user(
            session, user_id, username, full_name
        )
        
        # Удаляем старые ставки пользователя на этот турнир
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
        logger.error(f"Ошибка сохранения ставок: {e}", exc_info=True)
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
    Обновляет результаты из UFC Stats - ВЕСЬ кард
    """
    try:
        print(f"🔄 Ищу результаты для турнира: {event.title}")
        print(f"📅 Дата турнира: {event.date_utc.strftime('%d.%m.%Y')}")
        
        from ufc_stats_api import get_todays_ufc_event_results
        
        # Получаем ВСЕ бои подходящего турнира
        ufc_fights = get_todays_ufc_event_results()
        
        if not ufc_fights:
            print("❌ Не найден подходящий турнир на UFC Stats")
            return False
        
        print(f"📊 На UFC Stats найдено {len(ufc_fights)} боев")
        
        # Получаем ВСЕ бои из нашей базы
        db_fights = await get_fights_for_event(session, event.id)
        print(f"📊 В нашей базе: {len(db_fights)} боев")
        
        if len(db_fights) != len(ufc_fights):
            print(f"⚠️ Внимание! Разное количество боев: база={len(db_fights)}, UFC Stats={len(ufc_fights)}")
        
        updated = 0
        matched_fights = []
        
        # Сопоставляем ВСЕ бои по именам
        for db_fight in db_fights:
            found_match = False
            
            for ufc_fight in ufc_fights:
                # Приводим имена к нижнему регистру для сравнения
                db_f1 = db_fight.fighter1_name.lower()
                db_f2 = db_fight.fighter2_name.lower()
                ufc_f1 = ufc_fight['fighter1'].lower()
                ufc_f2 = ufc_fight['fighter2'].lower()
                
                # Проверяем оба варианта порядка бойцов
                if (db_f1 == ufc_f1 and db_f2 == ufc_f2) or (db_f1 == ufc_f2 and db_f2 == ufc_f1):
                    # Нашли совпадение
                    found_match = True
                    winner_name = ufc_fight['winner'].lower()
                    
                    # Определяем победителя в нашем формате
                    if winner_name == ufc_f1:
                        db_fight.winner = '1' if db_f1 == ufc_f1 else '2'
                    elif winner_name == ufc_f2:
                        db_fight.winner = '2' if db_f1 == ufc_f1 else '1'
                    elif winner_name == 'draw':
                        db_fight.winner = 'draw'
                    elif winner_name == 'nc':
                        db_fight.winner = 'nc'
                    else:
                        print(f"⚠️ Неизвестный результат: {winner_name}")
                        continue
                    
                    updated += 1
                    matched_fights.append(ufc_fight['fight_order'])
                    
                    print(f"✅ Бой {db_fight.fight_order}: {db_fight.fighter1_name} vs {db_fight.fighter2_name} → {db_fight.winner}")
                    break
            
            if not found_match:
                print(f"⚠️ Не найден в UFC Stats: {db_fight.fighter1_name} vs {db_fight.fighter2_name}")
        
        if updated > 0:
            await session.commit()
            print(f"🎉 ОБНОВЛЕНО {updated} БОЕВ ИЗ {len(db_fights)}")
            print(f"📈 Сопоставлены бои с номерами: {sorted(matched_fights)}")
            return True
        
        print("❌ Не удалось сопоставить ни одного боя")
        print("Проверьте:")
        print("1. Имена бойцов в базе и на UFC Stats")
        print("2. Что это тот же самый турнир")
        
        return False
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

async def update_fights_with_results(session: AsyncSession, event_id: int, results: List[Dict]) -> bool:
    """
    Обновляет бои результатами
    """
    try:
        fights = await get_fights_for_event(session, event_id)
        fights_dict = {f.fight_order: f for f in fights}
        
        updated_count = 0
        for result in results:
            fight_order = result.get('fight_order')
            if fight_order in fights_dict:
                fight = fights_dict[fight_order]
                if fight.winner is None:  # Обновляем только если нет результата
                    fight.winner = result.get('winner')
                    updated_count += 1
        
        if updated_count > 0:
            await session.commit()
            logger.info(f"Обновлены результаты для {updated_count} боев турнира {event_id}")
            return True
        
        return False
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка обновления боев: {e}")
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
                
                # Обновляем статус ставки
                bet.status = 'win'
                bet.points_earned = float(points)
                logger.info(f"✅ ВЫИГРЫШ: +{points} очков")
                
            elif fight.winner in ['draw', 'nc', 'cancelled', None]:
                # Бой не состоялся или нет результата
                cancelled_fights.append(bet.fight_id)
                bet.status = 'cancelled'
                bet.points_earned = 0.0
                logger.info(f"➖ ОТМЕНА: бой {fight.fight_order} - {fight.winner}")
                
            else:
                # Не угадал
                bet.status = 'lose'
                bet.points_earned = 0.0
                logger.info(f"❌ ПРОИГРЫШ")
        
        # Если есть отмененные бои и есть страховочная ставка
        if cancelled_fights and insurance_bet and not used_insurance:
            logger.info(f"Проверяем страховку для отмененных боев: {cancelled_fights}")
            
            fight = fights_dict.get(insurance_bet.fight_id)
            if fight and fight.winner == str(insurance_bet.chosen_fighter):
                points = float(insurance_bet.odds_at_bet) if insurance_bet.odds_at_bet else 0.0
                total_points += points
                insurance_bet.status = 'win'
                insurance_bet.points_earned = float(points)
                used_insurance = True
                logger.info(f"🛡️ СТРАХОВКА СЫГРАЛА: +{points} очков")
            else:
                insurance_bet.status = 'lose'
                insurance_bet.points_earned = 0.0
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
            if fight.winner is None or fight.winner == '':
                return False
        
        return True
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
            has_unfinished_fights = any(fight.winner is None for fight in fights)
            if has_unfinished_fights:
                unfinished_events.append(event)
    
    return unfinished_events