"""
Event Service - работа с турнирами UFC
Создание, получение, управление статусами событий
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from database import Event, Fight, User, Bet
from .database import parse_iso_date

logger = logging.getLogger(__name__)

# ============ СОЗДАНИЕ СОБЫТИЙ ============

async def debug_event_creation(session: AsyncSession, event_data: Dict, fights_data: List[Dict]):
    """Функция для отладки создания турнира"""
    try:
        logger.info("=" * 50)
        logger.info("ОТЛАДКА СОЗДАНИЯ ТУРНИРА")
        logger.info(f"event_data keys: {event_data.keys() if event_data else 'None'}")
        logger.info(f"event_data: {event_data}")
        logger.info(f"fights_data length: {len(fights_data) if fights_data else 0}")
        if fights_data:
            logger.info(f"First fight: {fights_data[0]}")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Ошибка в debug_event_creation: {e}")


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
async def get_event_by_id(session: AsyncSession, event_id: int) -> Optional[Event]:
    """Получает турнир по ID"""
    result = await session.execute(
        select(Event).where(Event.id == event_id)
    )
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
async def get_finished_events(session: AsyncSession) -> List[Event]:
    """Получает завершенные турниры"""
    result = await session.execute(
        select(Event)
        .where(Event.status == 'finished')
        .order_by(Event.date_utc.desc())
    )
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
