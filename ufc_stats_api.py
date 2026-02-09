"""
UFC Stats API - показывает ВЕСЬ кард турнира
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

def parse_date(date_str):
    """Парсит дату из UFC Stats формата"""
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
    ВОЗВРАЩАЕТ ВСЕ БОИ!
    """
    try:
        # 1. Получаем список всех турниров
        url = "http://ufcstats.com/statistics/events/completed"
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table', class_='b-statistics__table-events')
        if not table:
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
                    print(f"✅ Найден подходящий турнир: {event_name} ({event_date.strftime('%d.%m.%Y')})")
                    print(f"🔗 Ссылка: {event_url}")
                    
                    # 2. Получаем бои этого турнира - ВСЕ!
                    fights = get_event_fights(event_url)
                    return fights
                    
            except Exception as e:
                print(f"Ошибка обработки строки: {e}")
                continue
        
        print("❌ Не найден подходящий турнир (с датой <= сегодня)")
        return []
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []

def get_event_fights(event_url: str) -> list:
    """Получает ВСЕ бои конкретного турнира"""
    try:
        response = requests.get(event_url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        fights = []
        fights_table = soup.find('table', class_='b-fight-details__table')
        
        if not fights_table:
            print("❌ Не найдена таблица боев")
            return []
        
        rows = fights_table.find_all('tr')[1:]  # Пропускаем заголовок
        
        print(f"📊 Найдено строк в таблице: {len(rows)}")
        
        for i, row in enumerate(rows, 1):
            try:
                # Ищем бойцов
                fighter_links = row.find_all('a', class_='b-link_style_black')
                if len(fighter_links) >= 2:
                    fighter1 = fighter_links[0].get_text(strip=True)
                    fighter2 = fighter_links[1].get_text(strip=True)
                    
                    # Определяем победителя
                    winner = fighter1  # по умолчанию первый
                    
                    # Ищем маркеры
                    cells = row.find_all('td')
                    for cell in cells:
                        text = cell.get_text(strip=True)
                        if text == 'L':
                            winner = fighter2
                            break
                        elif text == 'D':
                            winner = 'draw'
                            break
                        elif text == 'NC':
                            winner = 'nc'
                            break
                    
                    fights.append({
                        'fight_order': i,  # Сохраняем порядковый номер
                        'fighter1': fighter1,
                        'fighter2': fighter2,
                        'winner': winner
                    })
                    
                    print(f"  Бой {i}: {fighter1} vs {fighter2} → {winner}")
                    
            except Exception as e:
                print(f"  ❌ Ошибка парсинга боя {i}: {e}")
                continue
        
        print(f"✅ Всего получено {len(fights)} боев")
        return fights
        
    except Exception as e:
        print(f"❌ Ошибка получения боев: {e}")
        return []