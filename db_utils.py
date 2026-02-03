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

async def get_event_by_id(session: AsyncSession, event_id: int) -> Optional[Event]:
    """Получает турнир по ID"""
    result = await session.execute(
        select(Event).where(Event.id == event_id)
    )
    return result.scalar_one_or_none()

# ==================== УТИЛИТЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ====================

async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str = None,
    full_name: str = None
) -> User:
    """Получает или создает пользователя"""
    result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            user_id=user_id,
            username=username,
            full_name=full_name
        )
        session.add(user)
        await session.commit()
        logger.info(f"Создан новый пользователь: {user_id}")
    
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
    bets_data: dict
) -> bool:
    """
    Сохраняет ставки пользователя в БД
    
    bets_data = {
        'main_bets': [{'fight_id': 1, 'chosen_fighter': 1, 'odds': 1.5}, ...],  # 5 ставок
        'insurance_bet': {'fight_id': 6, 'chosen_fighter': 2, 'odds': 2.1} или None
    }
    """
    try:
        # Проверяем, что пользователь существует
        user = await get_or_create_user(
            session, user_id, None, None
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