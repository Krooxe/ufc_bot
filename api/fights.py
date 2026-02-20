"""
UFC Fights API - парсинг боёв
"""
import logging
import re
import aiohttp
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def _get_fights_from_event(session: aiohttp.ClientSession, event_url: str) -> List[Dict]:
    """
    Получает все бои из события ufcstats.com
    Использует детальные страницы для сохранения правильного порядка бойцов
    """
    try:
        async with session.get(event_url, timeout=10) as response:
            if response.status != 200:
                logger.error(f"Ошибка HTTP {response.status} для {event_url}")
                return []
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            fights = []
            
            # DEBUG: Смотрим что на странице
            all_tables = soup.find_all("table")
            logger.info(f"DEBUG: Всего таблиц на странице: {len(all_tables)}")
            for i, t in enumerate(all_tables[:3], 1):
                classes = t.get('class', [])
                logger.info(f"DEBUG: Таблица {i} классы: {classes}")
            
            # Ищем таблицу с боями (может иметь несколько классов)
            fights_table = soup.find("table", class_=lambda x: x and "b-fight-details__table" in x)
            if not fights_table:
                fights_table = soup.find("table", class_=lambda x: x and "b-statistics__table" in x)
            
            logger.info(f"DEBUG: fights_table найдена: {fights_table is not None}")
            
            if fights_table:
                # Получаем ссылки на детальные страницы боёв из data-link атрибутов строк
                fight_links = []
                
                # Ищем все строки с data-link
                for tr in fights_table.find_all("tr", attrs={"data-link": True}):
                    fight_url = tr.get("data-link")
                    if fight_url and "fight-details" in fight_url and fight_url not in fight_links:
                        fight_links.append(fight_url)
                
                logger.info(f"Найдено {len(fight_links)} ссылок на детальные страницы боёв")
                
                # Парсим каждый бой детально
                for i, fight_url in enumerate(fight_links, 1):
                    try:
                        fighter1, fighter2 = await _parse_fight_details(session, fight_url)
                        fights.append({
                            'order': i,
                            'fighter1': fighter1,
                            'fighter2': fighter2,
                        })
                        logger.debug(f"Бой {i}: {fighter1} vs {fighter2}")
                    except Exception as e:
                        logger.warning(f"Ошибка парсинга боя {i} ({fight_url}): {e}")
                        # Добавляем заглушку
                        fights.append({
                            'order': i,
                            'fighter1': f"Fighter_{i}A",
                            'fighter2': f"Fighter_{i}B",
                        })
            
            logger.info(f"Успешно спарсено {len(fights)} боев")
            return fights
            
    except Exception as e:
        logger.error(f"Ошибка получения боев: {e}", exc_info=True)
        return []


async def _parse_fight_details(session: aiohttp.ClientSession, fight_url: str) -> Tuple[str, str]:
    """
    Парсит детальную страницу боя и возвращает имена бойцов в правильном порядке
    (первый = левый угол, второй = правый угол, независимо от победителя)
    """
    try:
        async with session.get(fight_url, timeout=10) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status}")
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Способ 1: Ищем ссылки на профили бойцов (самый надёжный)
            fighter_links = soup.find_all("a", class_="b-fight-details__person-link")
            
            if len(fighter_links) >= 2:
                fighter1 = fighter_links[0].text.strip()
                fighter2 = fighter_links[1].text.strip()
                return fighter1, fighter2
            
            # Способ 2: Пробуем другой селектор
            fighter_links = soup.find_all("a", href=re.compile("fighter-details"))
            
            if len(fighter_links) >= 2:
                fighter1 = fighter_links[0].text.strip()
                fighter2 = fighter_links[1].text.strip()
                return fighter1, fighter2
            
            # Способ 3: Ищем имена в таблице
            tables = soup.find_all("table", class_=lambda x: x and "b-fight-details__table" in x)
            for table in tables:
                rows = table.find_all("tr")
                if len(rows) >= 2:
                    cols = rows[1].find_all("td")
                    if len(cols) >= 2:
                        # Ищем имена в колонке с бойцами
                        fighter_cell = cols[1]
                        text = fighter_cell.get_text(strip=True)
                        
                        # Пробуем найти через vs
                        if " vs " in text:
                            parts = text.split(" vs ")
                            return parts[0].strip(), parts[1].strip()
                        
                        # Пробуем найти ссылки внутри ячейки
                        cell_links = fighter_cell.find_all("a")
                        if len(cell_links) >= 2:
                            return cell_links[0].text.strip(), cell_links[1].text.strip()
            
            # Способ 4: Последняя надежда - ищем любые ссылки на бойцов
            all_links = soup.find_all("a", href=re.compile("fighter-details"))
            if len(all_links) >= 2:
                # Берём первые две уникальные ссылки
                unique_names = []
                seen = set()
                for link in all_links:
                    name = link.text.strip()
                    if name and name not in seen and len(unique_names) < 2:
                        seen.add(name)
                        unique_names.append(name)
                
                if len(unique_names) >= 2:
                    return unique_names[0], unique_names[1]
            
            raise Exception("Не удалось найти имена бойцов ни одним способом")
            
    except Exception as e:
        logger.error(f"Ошибка парсинга детальной страницы {fight_url}: {e}")
        raise


async def _get_fights_old(session: aiohttp.ClientSession, event_url: str) -> List[Dict]:
    """
    Старый метод парсинга с главной страницы (оставляем для обратной совместимости)
    Может возвращать неправильный порядок для завершённых турниров
    """
    try:
        async with session.get(event_url, timeout=10) as response:
            if response.status != 200:
                return []
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            fights = []
            # Исправленный поиск таблицы
            fights_table = soup.find("table", class_=lambda x: x and "b-fight-details__table" in x)
            
            if fights_table:
                fight_rows = fights_table.find_all("tr")[1:]
                
                for i, row in enumerate(fight_rows, 1):
                    try:
                        cols = row.find_all("td")
                        if len(cols) >= 2:
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
                        continue
            
            return fights
            
    except Exception as e:
        return []


def get_event_fights(event: Dict) -> List[Dict]:
    """
    Извлекает бои из структуры события (синхронная обёртка)
    Используется для преобразования формата
    """
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


async def test_fight_parser(fight_url: str):
    """
    Тестовая функция для отладки парсера боёв
    """
    async with aiohttp.ClientSession() as session:
        try:
            fighter1, fighter2 = await _parse_fight_details(session, fight_url)
            print(f"✅ Успех: {fighter1} vs {fighter2}")
            return fighter1, fighter2
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return None, None


if __name__ == "__main__":
    # Тестовый запуск
    import asyncio
    test_url = "http://ufcstats.com/fight-details/5d1e156cc2869cd9"
    asyncio.run(test_fight_parser(test_url))