"""
UFC Fights API - парсинг боёв
"""
import logging
import aiohttp
from typing import List, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def _get_fights_from_event(session: aiohttp.ClientSession, event_url: str) -> List[Dict]:
    """Получает все бои из события ufcstats.com"""
    try:
        async with session.get(event_url, timeout=10) as response:
            if response.status != 200:
                logger.error(f"Ошибка HTTP {response.status} для {event_url}")
                return []
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            fights = []
            
            # Ищем таблицу с боями
            fights_table = soup.find("table", {"class": "b-fight-details__table"})
            if not fights_table:
                fights_table = soup.find("table", {"class": "b-statistics__table"})
            
            if fights_table:
                fight_rows = fights_table.find_all("tr")[1:]  # Пропускаем заголовок
                
                for i, row in enumerate(fight_rows, 1):
                    try:
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            # Получаем имена бойцов
                            fighters = row.find_all("a", class_="b-link")
                            
                            if len(fighters) >= 2:
                                fighter1 = fighters[0].text.strip()
                                fighter2 = fighters[1].text.strip()
                                
                                fights.append({
                                    'order': i,
                                    'fighter1': fighter1,
                                    'fighter2': fighter2,
                                })
                    except Exception as e:
                        logger.warning(f"Ошибка парсинга строки {i}: {e}")
                        continue
            
            logger.info(f"Успешно спарсено {len(fights)} боев")
            return fights
            
    except Exception as e:
        logger.error(f"Ошибка получения боев: {e}")
        return []


def get_event_fights(event: Dict) -> List[Dict]:
    """Извлекает бои из структуры события"""
    fights = event.get('fights', [])
    
    result = []
    for fight in fights:
        result.append({
            'fighter1': {'name': fight['fighter1'], 'id': None},
            'fighter2': {'name': fight['fighter2'], 'id': None},
            'competition_id': f'fight-{fight["order"]}',
            'status': 'scheduled'
        })
    
    return result
