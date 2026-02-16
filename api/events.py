"""
UFC Events API
Получение информации о турнирах UFC с ufcstats.com
"""
import logging
import aiohttp
import re
from typing import Dict, Optional, List
from datetime import datetime, timezone
from bs4 import BeautifulSoup

import config
from .test_data import get_test_ppv_event

logger = logging.getLogger(__name__)

# UFCStats.com - источник данных
UFCSTATS_COMPLETED_URL = "http://ufcstats.com/statistics/events/completed"


async def get_upcoming_event() -> Optional[Dict]:
    """
    Получает турнир с ufcstats.com
    
    На странице /statistics/events/completed:
    - Индекс 0 = ПРЕДСТОЯЩИЙ турнир (для продакшена)
    - Индекс 1 = Завершённый турнир (для DEBUG тестирования)
    
    Returns:
        Dict | None: Данные турнира с боями
    """
    # Индекс турнира: 0 = предстоящий, 1 = завершённый (для DEBUG)
    event_index = 1 if config.DEBUG_MODE else 0
    
    try:
        async with aiohttp.ClientSession() as session:
            # 1. Получаем список турниров
            async with session.get(UFCSTATS_COMPLETED_URL, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Ошибка ufcstats.com: статус {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Находим все ссылки на события
                event_links = soup.find_all("a", href=re.compile("event-details"))
                if not event_links:
                    logger.error("Не найдено турниров")
                    return None
                
                if len(event_links) <= event_index:
                    logger.error(f"Недостаточно турниров (нужен индекс {event_index})")
                    return None
                
                # Берём турнир по индексу
                link = event_links[event_index]
                event_url = link["href"]
                event_title = link.text.strip()
                
                if config.DEBUG_MODE:
                    logger.info(f"🧪 DEBUG_MODE: Беру завершённый турнир (индекс {event_index}) для тестирования")
                else:
                    logger.info(f"🏆 PRODUCTION: Беру предстоящий турнир (индекс {event_index})")
                
                # Парсим дату
                parent_td = link.find_parent('td')
                event_date = datetime.now(timezone.utc)
                
                if parent_td:
                    date_match = re.search(
                        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', 
                        parent_td.text
                    )
                    if date_match:
                        event_date = datetime.strptime(date_match.group(), "%B %d, %Y").replace(
                            tzinfo=timezone.utc, hour=18
                        )
                
                logger.info(f"Найден турнир: {event_title}")
            
            # 2. Получаем бои этого турнира
            from ufc_api import _get_fights_from_event
            fights = await _get_fights_from_event(session, event_url)
            
            logger.info(f"Получено боёв: {len(fights)}")
            
            # Формируем ответ
            return {
                'id': None,
                'name': event_title,
                'shortName': event_title[:30],
                'date': event_date.isoformat().replace('+00:00', 'Z'),
                'url': event_url,
                'fights': fights,
            }
            
    except Exception as e:
        logger.error(f"Ошибка получения турнира: {e}", exc_info=True)
        return None


async def get_next_ppv_event() -> Optional[Dict]:
    """
    Получает следующий PPV турнир для создания в админке
    
    В DEBUG_MODE возвращает тестовые данные.
    В продакшене парсит с ufcstats.com.
    
    Returns:
        Dict | None: Данные турнира в формате {event: {...}, fights: [...]}
    """
    # Получаем турнир
    event_data = await get_upcoming_event()
    
    if not event_data:
        logger.warning("Не удалось получить турнир")
        return None
    
    # Преобразуем в формат для db_utils.create_event_from_api()
    return {
        'event': {
            'id': event_data.get('id'),
            'name': event_data.get('name'),
            'shortName': event_data.get('shortName'),
            'date': event_data.get('date'),
            'url': event_data.get('url'),
        },
        'fights': event_data.get('fights', [])
    }


async def get_completed_event_for_results(index: int = 1) -> Optional[Dict]:
    """
    Получает завершённый турнир для закрытия и расчёта результатов
    
    Args:
        index: Индекс турнира (1 = второй в списке = только что завершился)
    
    Returns:
        Dict | None: Данные турнира с результатами боёв
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(UFCSTATS_COMPLETED_URL, timeout=10) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                event_links = soup.find_all("a", href=re.compile("event-details"))
                if len(event_links) <= index:
                    logger.error(f"Недостаточно турниров (запрошен индекс {index})")
                    return None
                
                # Берем турнир по индексу (1 = второй = только что завершился)
                link = event_links[index]
                event_url = link["href"]
                event_title = link.text.strip()
                
                logger.info(f"Получаю результаты турнира: {event_title}")
                
                # Получаем бои с результатами
                from ufc_api import _get_fights_from_event
                fights = await _get_fights_from_event(session, event_url)
                
                return {
                    'name': event_title,
                    'url': event_url,
                    'fights': fights
                }
                
    except Exception as e:
        logger.error(f"Ошибка получения завершённого турнира: {e}")
        return None
