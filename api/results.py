"""
UFC Results API - получение результатов турниров
Парсинг результатов боёв с ufcstats.com
"""
import logging
import requests
import aiohttp
from typing import Optional, List, Dict
from datetime import datetime
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Парсит дату из UFC Stats формата
    
    Args:
        date_str: Строка с датой (например "February 07, 2024")
        
    Returns:
        datetime или None если не удалось распарсить
    """
    try:
        date_str = date_str.strip()
        for fmt in ('%B %d, %Y', '%b %d, %Y'):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
    except Exception:
        return None


def get_todays_ufc_event_results() -> list:
    """
    Находит турнир с датой сегодня или ранее и возвращает его результаты
    
    ВАЖНО: Возвращает ВСЕ бои с определёнными победителями!
    
    Returns:
        List[Dict]: Список боёв с победителями
            [{
                'fight_order': 1,
                'fighter1': 'Name A',
                'fighter2': 'Name B',
                'winner': 'Name A' | 'draw' | 'nc'
            }]
    """
    try:
        # 1. Получаем список всех турниров
        url = "http://ufcstats.com/statistics/events/completed"
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table', class_='b-statistics__table-events')
        if not table:
            logger.error("Не найдена таблица турниров")
            return []
        
        rows = table.find_all('tr')[1:]  # Пропускаем заголовок
        today = datetime.now()
        
        for row in rows:
            try:
                # Получаем ссылку и название
                link = row.find('a')
                if not link:
                    continue
                    
                event_url = link.get('href')
                event_name = link.get_text(strip=True)
                
                # Парсим дату из строки
                full_text = row.get_text(strip=True)
                date_match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', full_text)
                
                if not date_match:
                    continue
                    
                event_date = parse_date(date_match.group(1))
                if not event_date:
                    continue
                
                # Проверяем что турнир уже прошел (дата <= сегодня)
                if event_date <= today:
                    logger.info(f"Найден завершённый турнир: {event_name} ({event_date.strftime('%d.%m.%Y')})")
                    
                    # 2. Получаем бои этого турнира - ВСЕ!
                    fights = get_event_fights(event_url)
                    return fights
                    
            except Exception as e:
                logger.warning(f"Ошибка обработки турнира: {e}")
                continue
        
        logger.warning("Не найден подходящий турнир (с датой <= сегодня)")
        return []
        
    except Exception as e:
        logger.error(f"Ошибка get_todays_ufc_event_results: {e}")
        return []


def get_event_fights(event_url: str) -> list:
    """
    Получает ВСЕ бои конкретного турнира с результатами
    
    Args:
        event_url: URL турнира на ufcstats.com
        
    Returns:
        List[Dict]: Список боёв с результатами
    """
    try:
        response = requests.get(event_url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        fights = []
        fights_table = soup.find('table', class_='b-fight-details__table')
        
        if not fights_table:
            logger.error("Не найдена таблица боев")
            return []
        
        rows = fights_table.find_all('tr')[1:]  # Пропускаем заголовок
        
        logger.info(f"Найдено строк в таблице: {len(rows)}")
        
        for i, row in enumerate(rows, 1):
            try:
                # Ищем бойцов
                fighter_links = row.find_all('a', class_='b-link_style_black')
                if len(fighter_links) >= 2:
                    fighter1 = fighter_links[0].get_text(strip=True)
                    fighter2 = fighter_links[1].get_text(strip=True)
                    
                    # Определяем победителя
                    winner = fighter1  # по умолчанию первый
                    
                    # Ищем маркеры W/L/D/NC
                    cells = row.find_all('td')
                    for cell in cells:
                        text = cell.get_text(strip=True)
                        if text == 'L':  # Loss - проиграл первый
                            winner = fighter2
                            break
                        elif text == 'D':  # Draw - ничья
                            winner = 'draw'
                            break
                        elif text == 'NC':  # No Contest
                            winner = 'nc'
                            break
                    
                    fights.append({
                        'fight_order': i,
                        'fighter1': fighter1,
                        'fighter2': fighter2,
                        'winner': winner
                    })
                    
                    logger.debug(f"Бой {i}: {fighter1} vs {fighter2} → {winner}")
                    
            except Exception as e:
                logger.warning(f"Ошибка парсинга боя {i}: {e}")
                continue
        
        logger.info(f"Всего получено {len(fights)} боев")
        return fights
        
    except Exception as e:
        logger.error(f"Ошибка получения боев: {e}")
        return []


async def fetch_event_results(event_api_id: str) -> Optional[List[Dict]]:
    """
    Получает результаты турнира (асинхронная версия)
    
    TODO: Реализовать асинхронную версию если нужно
    Пока используйте get_todays_ufc_event_results()
    """
    # Можно вызвать синхронную версию
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, get_todays_ufc_event_results)
    return result
