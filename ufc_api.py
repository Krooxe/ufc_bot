"""
ufc_api.py - Получение данных о UFC событиях из ufcstats.com
ЧИСТЫЙ код, без косяков
"""

import aiohttp
import asyncio
import logging
from datetime import datetime, timezone
import re
from typing import Optional, Dict, List
from bs4 import BeautifulSoup
import config

logger = logging.getLogger(__name__)

UFCSTATS_COMPLETED_URL = "http://ufcstats.com/statistics/events/completed"


async def get_upcoming_event() -> Optional[Dict]:
    """
    Основная функция: получает турнир для создания PPV
    Берет ПЕРВЫЙ турнир (самый свежий) с ufcstats.com
    """
    if config.DEBUG_MODE:
        return _get_test_ppv_event()
    
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
                
                # Берем ПЕРВУЮ ссылку (индекс 0)
                link = event_links[0]
                event_url = link["href"]
                event_title = link.text.strip()
                
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
            fights = await _get_fights_from_event(session, event_url)
            
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
        logger.error(f"Ошибка получения турнира: {e}")
        return None


async def _get_fights_from_event(session: aiohttp.ClientSession, event_url: str) -> List[Dict]:
    """
    Получает все бои из события ufcstats.com (парсит напрямую со страницы турнира)
    """
    try:
        async with session.get(event_url, timeout=10) as response:
            if response.status != 200:
                logger.error(f"Ошибка HTTP {response.status} для {event_url}")
                return []
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # ДЛЯ ОТЛАДКИ: сохраним HTML чтобы посмотреть структуру
            with open("debug_event_page.html", "w", encoding="utf-8") as f:
                f.write(html[:5000])  # Первые 5000 символов
            
            # Ищем ВСЕХ бойцов на странице турнира
            # На странице турнира бойцы в таблице или списке
            
            # Попробуем разные способы:
            
            # Способ 1: Ищем таблицу с боями по ID или классу
            fights_table = soup.find("table", {"class": "b-fight-details__table"})
            if not fights_table:
                # Ищем по другим классам
                fights_table = soup.find("table", {"class": "b-statistics__table"})
            
            # Способ 2: Ищем все строки с боями
            fight_rows = []
            if fights_table:
                fight_rows = fights_table.find_all("tr")[1:]  # Пропускаем заголовок
            else:
                # Ищем все строки таблиц вообще
                all_tables = soup.find_all("table")
                for table in all_tables:
                    rows = table.find_all("tr")
                    if len(rows) > 5:  # Если таблица имеет несколько строк
                        fight_rows = rows[1:]  # Пропускаем заголовок
                        break
            
            logger.info(f"Найдено строк с боями: {len(fight_rows)}")
            
            if not fight_rows:
                # Способ 3: Ищем бойцов по ссылкам с именами
                fighter_links = soup.find_all("a", class_="b-link_style_black")
                fighters = []
                for link in fighter_links:
                    name = link.text.strip()
                    if name and name not in fighters:
                        fighters.append(name)
                
                # Группируем по парам
                fights = []
                for i in range(0, len(fighters), 2):
                    if i + 1 < len(fighters):
                        fights.append({
                            'order': len(fights) + 1,
                            'fighter1': fighters[i],
                            'fighter2': fighters[i + 1],
                        })
                
                logger.info(f"Найдено боев через ссылки: {len(fights)}")
                return fights
            
            # Парсим бои из строк таблицы
            fights = []
            for i, row in enumerate(fight_rows, 1):
                try:
                    # Ищем имена бойцов в строке
                    fighter_cells = row.find_all("td")
                    
                    # Обычно имена во второй ячейке (индекс 1)
                    if len(fighter_cells) >= 2:
                        names_cell = fighter_cells[1]
                        
                        # Ищем имена бойцов в ячейке
                        fighter_names = []
                        
                        # Ищем ссылки с именами
                        name_links = names_cell.find_all("a", class_="b-link_style_black")
                        if name_links and len(name_links) >= 2:
                            fighter_names = [link.text.strip() for link in name_links[:2]]
                        else:
                            # Пробуем парсить текст ячейки
                            cell_text = names_cell.get_text(strip=True)
                            # Разделяем имена (обычно разделены двойным пробелом)
                            if '  ' in cell_text:
                                fighter_names = cell_text.split('  ')[:2]
                            else:
                                continue
                        
                        if len(fighter_names) >= 2:
                            fights.append({
                                'order': i,
                                'fighter1': fighter_names[0],
                                'fighter2': fighter_names[1],
                            })
                            logger.debug(f"Бой {i}: {fighter_names[0]} vs {fighter_names[1]}")
                            
                except Exception as e:
                    logger.warning(f"Ошибка парсинга строки {i}: {e}")
                    continue
            
            logger.info(f"Успешно спарсено {len(fights)} боев")
            
            # Если всё еще 0 боев, попробуем самый простой способ
            if not fights:
                # Ищем ВСЕ имена бойцов на странице
                all_fighter_names = []
                
                # Ищем в разных местах
                for tag in soup.find_all(['a', 'span', 'div', 'td']):
                    text = tag.get_text(strip=True)
                    # Фильтруем короткие тексты и не-имена
                    if (len(text) > 3 and len(text) < 50 and 
                        not text.isdigit() and 
                        'UFC' not in text and 
                        'Event' not in text and
                        'Date' not in text and
                        'Location' not in text):
                        
                        # Проверяем, похоже ли на имя бойца
                        if any(word.istitle() for word in text.split()):
                            if text not in all_fighter_names:
                                all_fighter_names.append(text)
                
                # Группируем по парам (первые 20 имен)
                valid_names = all_fighter_names[:20]
                for i in range(0, len(valid_names), 2):
                    if i + 1 < len(valid_names):
                        fights.append({
                            'order': len(fights) + 1,
                            'fighter1': valid_names[i],
                            'fighter2': valid_names[i + 1],
                        })
                
                logger.info(f"Найдено боев через все имена: {len(fights)}")
            
            return fights
            
    except Exception as e:
        logger.error(f"Ошибка получения боев: {e}")
        return []


async def _parse_fight_names(session: aiohttp.ClientSession, fight_url: str) -> tuple:
    """Парсит имена бойцов с детальной страницы"""
    try:
        async with session.get(fight_url, timeout=10) as response:
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Ищем имена в детальной странице боя
            fighters = []
            
            # Способ 1: Ищем по классу b-fight-details__person-link
            fighter_elements = soup.find_all("a", class_="b-fight-details__person-link")
            
            # Способ 2: Ищем по другим возможным классам
            if not fighter_elements:
                fighter_elements = soup.find_all("a", class_="b-link_style_black")
            
            for element in fighter_elements[:2]:  # Берем только первых двух
                name = element.text.strip()
                if name and name not in fighters:
                    fighters.append(name)
            
            if len(fighters) >= 2:
                return fighters[0], fighters[1]
            else:
                raise Exception(f"Не удалось получить обоих бойцов. Найдено: {fighters}")
                
    except Exception as e:
        logger.error(f"Ошибка парсинга боя {fight_url}: {e}")
        raise


def get_event_fights(event: Dict) -> List[Dict]:
    """
    Извлекает бои из структуры события для обратной совместимости
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
    
    logger.info(f"Извлечено боев: {len(result)}")
    return result


# ==================== ТЕСТОВЫЕ ДАННЫЕ ====================

def _get_test_ppv_event() -> Dict:
    """Тестовый турнир (только для DEBUG_MODE)"""
    from datetime import timedelta
    
    event_date = datetime.now(timezone.utc) + timedelta(days=7)
    
    return {
        'id': None,
        'name': 'UFC 305: Тестовый турнир',
        'shortName': 'UFC 305',
        'date': event_date.isoformat().replace('+00:00', 'Z'),
        'url': 'http://ufcstats.com/event-details/test',
        'fights': [
            {
                'order': i,
                'fighter1': f'Боец {i}A',
                'fighter2': f'Боец {i}B',
            }
            for i in range(1, 13)
        ]
    }


async def fetch_event_results(event_api_id: str) -> Optional[List[Dict]]:
    """Заглушка для результатов"""
    if config.DEBUG_MODE:
        return _get_test_results()
    return None


def _get_test_results() -> List[Dict]:
    """Тестовые результаты"""
    return [
        {'fight_order': 1, 'fighter1_name': 'Боец 1A', 'fighter2_name': 'Боец 1B', 'winner': '1', 'method': 'KO'},
    ]


# ==================== ТЕСТ ====================

async def test_api():
    """Тест работы API"""
    print("🔍 Тестирование UFC Stats API...")
    
    event = await get_upcoming_event()
    
    if not event:
        print("❌ Не удалось получить событие")
        return
    
    print(f"✅ Турнир: {event.get('name')}")
    
    fights = get_event_fights(event)
    print(f"🥊 Боев: {len(fights)}")
    
    for i, fight in enumerate(fights[:5], 1):  # Показываем первые 5
        f1 = fight.get('fighter1', {}).get('name', 'N/A')
        f2 = fight.get('fighter2', {}).get('name', 'N/A')
        print(f"  {i:2}. {f1:25} vs {f2}")
    
    if len(fights) > 5:
        print(f"  ... и ещё {len(fights) - 5} боев")


if __name__ == "__main__":
    asyncio.run(test_api())