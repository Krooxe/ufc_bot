import aiohttp
import asyncio
import logging
from datetime import datetime
import re
from typing import Optional, Dict, List, Any
import config

logger = logging.getLogger(__name__)

# Новый URL ESPN API
ESPN_API_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"

async def fetch_upcoming_events() -> Optional[List[Dict]]:
    """
    Получает список предстоящих событий UFC из ESPN API
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ESPN_API_URL, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    events = data.get('events', [])
                    logger.info(f"Получено событий от ESPN: {len(events)}")
                    return events
                else:
                    logger.error(f"Ошибка ESPN API: статус {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при запросе к ESPN API: {e}")
        return None

def parse_espn_date(date_string: str) -> datetime:
    """
    Парсит дату из формата ESPN API с учетом часового пояса
    Пример: "2024-05-04T23:00Z"
    """
    try:
        # ESPN использует ISO формат с Z (UTC)
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return dt
    except Exception as e:
        logger.error(f"Ошибка парсинга даты ESPN '{date_string}': {e}")
        return datetime.now(timezone.utc)  # Возвращаем текущее время UTC

def is_ppv_event(event: Dict) -> bool:
    """
    Проверяет, является ли событие номерным PPV турниром в ESPN API
    """
    # Получаем название события
    name = event.get('name', '').lower()
    short_name = event.get('shortName', '').lower()
    
    # Проверяем по ключевым словам
    check_name = name + " " + short_name
    
    # Исключаем не-PPV события
    if any(exclude in check_name for exclude in ['fight night', 'fn', 'on espn', 'apex', 'ufc on']):
        return False
    
    # Ищем паттерн "UFC" + пробел + цифры
    pattern = r'ufc\s+\d+'
    if re.search(pattern, check_name, re.IGNORECASE):
        return True
    
    # Дополнительная проверка: если в названии есть номер и нет исключающих слов
    if re.search(r'\d+', check_name) and 'ufc' in check_name:
        return True
    
    return False

from datetime import datetime, timezone  # ИМПОРТИРУЕМ timezone

def get_next_ppv_event(events: List[Dict]) -> Optional[Dict]:
    """
    Находит следующий номерной PPV турнир из ESPN данных
    """
    if not events:
        return None
    
    current_time = datetime.now(timezone.utc)  # Используем timezone-aware дату
    
    # Фильтруем только будущие события
    future_events = []
    for event in events:
        date_str = event.get('date', '')
        if date_str:
            event_date = parse_espn_date(date_str)
            # Делаем event_date тоже timezone-aware
            if event_date.tzinfo is None:
                event_date = event_date.replace(tzinfo=timezone.utc)
            
            if event_date > current_time:
                future_events.append(event)
    
    # Фильтруем PPV события
    ppv_events = [event for event in future_events if is_ppv_event(event)]
    
    if not ppv_events:
        logger.info("PPV события не найдены. Доступные события:")
        for event in future_events[:3]:
            logger.info(f"  - {event.get('name', 'N/A')}")
        return None
    
    # Сортируем по дате (ближайшие первыми)
    ppv_events.sort(key=lambda x: parse_espn_date(x.get('date', '')))
    
    # Берем самое ближайшее
    next_event = ppv_events[0]
    
    logger.info(f"Найден PPV: {next_event.get('name')}")
    logger.info(f"Дата: {next_event.get('date')}")
    logger.info(f"ID: {next_event.get('id')}")
    
    return next_event

def get_event_fights_from_espn(event: Dict) -> List[Dict]:
    """
    Извлекает бои из события ESPN API
    """
    fights = []
    
    # В ESPN бои находятся в competitions
    competitions = event.get('competitions', [])
    
    for comp in competitions:
        competitors = comp.get('competitors', [])
        if len(competitors) >= 2:
            # Получаем имена бойцов
            fighter1 = competitors[0].get('athlete', {}).get('displayName', 'N/A')
            fighter2 = competitors[1].get('athlete', {}).get('displayName', 'N/A')
            
            # Получаем дополнительные данные
            fighter1_id = competitors[0].get('athlete', {}).get('id')
            fighter2_id = competitors[1].get('athlete', {}).get('id')
            
            fights.append({
                'fighter1': {'name': fighter1, 'id': fighter1_id},
                'fighter2': {'name': fighter2, 'id': fighter2_id},
                'competition_id': comp.get('id'),
                'status': 'scheduled'  # ESPN не дает статус confirmed
            })
    
    logger.info(f"Извлечено боев из ESPN: {len(fights)}")
    return fights

# ==================== ТЕСТОВЫЙ ЗАПУСК ====================

async def test_espn_api():
    """Тестирование ESPN API"""
    print("🔍 Тестирование ESPN UFC API...")
    
    # Получаем события
    events = await fetch_upcoming_events()
    
    if not events:
        print("❌ Не удалось получить события от ESPN")
        return
    
    print(f"✅ Получено событий: {len(events)}")
    
    # Покажем все события для отладки
    print("\n📅 Все предстоящие события:")
    for i, event in enumerate(events[:5], 1):  # Показываем первые 5
        event_date = parse_espn_date(event.get('date', ''))
        date_str = event_date.strftime("%d.%m.%Y")
        print(f"  {i}. {event.get('name', 'N/A')} - {date_str}")
    
    # Ищем следующий PPV
    next_ppv = get_next_ppv_event(events)
    
    if next_ppv:
        print(f"\n🎉 Найден следующий PPV турнир:")
        print(f"   Название: {next_ppv.get('name')}")
        
        event_date = parse_espn_date(next_ppv.get('date', ''))
        date_str = event_date.strftime("%d.%m.%Y %H:%M UTC")
        print(f"   Дата: {date_str}")
        print(f"   ID: {next_ppv.get('id')}")
        
        # Получаем бои
        fights = get_event_fights_from_espn(next_ppv)
        print(f"   Боев: {len(fights)}")
        
        for i, fight in enumerate(fights[:5], 1):  # Показываем первые 5
            fighter1 = fight.get('fighter1', {}).get('name', 'N/A')
            fighter2 = fight.get('fighter2', {}).get('name', 'N/A')
            print(f"   {i}. {fighter1} vs {fighter2}")
    else:
        print("\n❌ PPV турниры не найдены среди событий")






# ==================== ТЕСТОВЫЕ ДАННЫЕ (для режима разработки) ====================

def get_test_ppv_event() -> Dict:
    """Возвращает тестовый PPV турнир для разработки"""
    from datetime import datetime, timedelta, timezone
    
    # Турнир через 7 дней от текущей даты
    event_date = datetime.now(timezone.utc) + timedelta(days=7)
    
    return {
        'id': 123456,  # ИЗМЕНИТЬ: был 'test-123', теперь число!
        'name': 'UFC 305: Тестовый турнир',
        'shortName': 'UFC 305',
        'date': event_date.isoformat().replace('+00:00', 'Z'),
        'competitions': [
            {
                'id': f'fight-{i}',
                'competitors': [
                    {
                        'athlete': {
                            'id': f'fighter_{i}_1',
                            'displayName': f'Тестовый Боец {i}A',
                            'shortName': f'Fighter{i}A'
                        }
                    },
                    {
                        'athlete': {
                            'id': f'fighter_{i}_2',
                            'displayName': f'Тестовый Боец {i}B',
                            'shortName': f'Fighter{i}B'
                        }
                    }
                ]
            }
            for i in range(1, 7)  # 5 тестовых боев
        ]
    }

async def fetch_upcoming_events_with_fallback() -> Optional[List[Dict]]:
    """
    Получает события с fallback на тестовые данные если API не работает
    или включен DEBUG_MODE
    """
    if config.DEBUG_MODE:
        logger.info("Используем тестовые данные (DEBUG_MODE=True)")
        return [get_test_ppv_event()]
    
    # Пробуем получить реальные данные
    events = await fetch_upcoming_events()
    
    # Если не получили или список пустой, используем тестовые данные
    if not events:
        logger.info("API не вернул данные, используем тестовые")
        return [get_test_ppv_event()]
    
    return events

async def fetch_event_results(event_api_id: str) -> Optional[List[Dict]]:
    """
    Получает результаты завершенного турнира по его API ID
    Возвращает список боев с результатами
    """
    if config.DEBUG_MODE:
        logger.info("Используем тестовые результаты (DEBUG_MODE=True)")
        return get_test_results()
    
    try:
        # ESPN API для результатов
        url = f"https://site.api.espn.com/apis/site/v2/sports/mma/ufc/summary?event={event_api_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return parse_event_results(data)
                else:
                    logger.error(f"Ошибка ESPN API для event {event_api_id}: статус {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка получения результатов: {e}")
        return None

def parse_event_results(event_data: Dict) -> List[Dict]:
    """
    Парсит результаты боев из данных ESPN
    """
    fights = []
    
    competitions = event_data.get('competitions', [])
    
    for i, comp in enumerate(competitions, 1):
        competitors = comp.get('competitors', [])
        if len(competitors) >= 2:
            fighter1 = competitors[0].get('athlete', {}).get('displayName', 'N/A')
            fighter2 = competitors[1].get('athlete', {}).get('displayName', 'N/A')
            
            # Статус боя
            status_type = comp.get('status', {}).get('type', {})
            status_name = status_type.get('name', '').lower()
            status_detail = status_type.get('detail', '').lower()
            
            winner = None
            method = ''
            
            # Определяем победителя по статусу
            if 'final' in status_name or 'result' in status_name:
                # Бой завершен - проверяем who победил
                for idx, competitor in enumerate(competitors, 1):
                    if competitor.get('winner', False):
                        winner = str(idx)
                        break
                
                # Если не нашли winner флаг, проверяем по очкам (если есть)
                if not winner and 'score' in comp:
                    score1 = competitors[0].get('score', '0')
                    score2 = competitors[1].get('score', '0')
                    if score1 > score2:
                        winner = '1'
                    elif score2 > score1:
                        winner = '2'
                    else:
                        winner = 'draw'
                
                method = status_detail
            
            elif 'no contest' in status_name or 'nc' in status_name:
                winner = 'nc'
                method = 'No Contest'
            
            elif 'draw' in status_name:
                winner = 'draw'
                method = 'Draw'
            
            elif 'canceled' in status_name or 'cancelled' in status_name:
                winner = 'cancelled'
                method = 'Canceled'
            
            # Если статус 'scheduled' или 'in progress' - winner остается None
            
            fights.append({
                'fight_order': i,  # Порядковый номер
                'fighter1_name': fighter1,
                'fighter2_name': fighter2,
                'winner': winner,  # None если бой еще не завершен
                'method': method,
                'status': status_name
            })
    
    return fights

def get_test_results() -> List[Dict]:
    """Тестовые результаты для отладки"""
    return [
        {'fight_order': 1, 'fighter1_name': 'Тестовый Боец 1A', 'fighter2_name': 'Тестовый Боец 1B', 'winner': '1', 'method': 'KO'},
        {'fight_order': 2, 'fighter1_name': 'Тестовый Боец 2A', 'fighter2_name': 'Тестовый Боец 2B', 'winner': '2', 'method': 'Submission'},
        {'fight_order': 3, 'fighter1_name': 'Тестовый Боец 3A', 'fighter2_name': 'Тестовый Боец 3B', 'winner': '1', 'method': 'Decision'},
        {'fight_order': 4, 'fighter1_name': 'Тестовый Боец 4A', 'fighter2_name': 'Тестовый Боец 4B', 'winner': 'nc', 'method': 'No Contest'},
        {'fight_order': 5, 'fighter1_name': 'Тестовый Боец 5A', 'fighter2_name': 'Тестовый Боец 5B', 'winner': 'draw', 'method': 'Draw'},
        {'fight_order': 6, 'fighter1_name': 'Тестовый Боец 6A', 'fighter2_name': 'Тестовый Боец 6B', 'winner': '1', 'method': 'TKO'},
    ]

if __name__ == "__main__":
    asyncio.run(test_espn_api())