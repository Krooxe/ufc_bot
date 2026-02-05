"""
Консольный скрипт для проверки реальных турниров с ESPN API
Без изменения основного бота, без сохранения в БД
"""
import asyncio
import aiohttp
import sys
import os
from datetime import datetime
from typing import List, Dict, Optional

# Добавляем путь для импорта, если нужно
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Константы из оригинального кода
ESPN_API_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"


def parse_espn_date(date_string: str) -> datetime:
    """Парсит дату из формата ESPN API"""
    try:
        # ESPN использует ISO формат с Z (UTC)
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return dt
    except Exception:
        return datetime.now()


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
                    print(f"✅ Получено событий от ESPN: {len(events)}")
                    return events
                else:
                    print(f"❌ Ошибка ESPN API: статус {response.status}")
                    return None
    except Exception as e:
        print(f"❌ Ошибка при запросе к ESPN API: {e}")
        return None


def get_event_fights(event: Dict) -> List[Dict]:
    """
    Извлекает ВСЕ бои из события ESPN API
    """
    fights = []
    
    # В ESPN бои находятся в competitions
    competitions = event.get('competitions', [])
    
    print(f"\n📊 Извлекаем бои из турнира...")
    
    for i, comp in enumerate(competitions, 1):
        competitors = comp.get('competitors', [])
        if len(competitors) >= 2:
            # Получаем имена бойцов
            fighter1 = competitors[0].get('athlete', {}).get('displayName', 'Боец 1')
            fighter2 = competitors[1].get('athlete', {}).get('displayName', 'Боец 2')
            
            # Получаем рекорды если есть
            fighter1_record = competitors[0].get('athlete', {}).get('record', '')
            fighter2_record = competitors[1].get('athlete', {}).get('record', '')
            
            fights.append({
                'number': i,
                'fighter1': fighter1,
                'fighter2': fighter2,
                'fighter1_record': fighter1_record,
                'fighter2_record': fighter2_record,
                'status': comp.get('status', {}).get('type', {}).get('name', 'scheduled')
            })
    
    print(f"✅ Извлечено боев: {len(fights)}")
    return fights


def display_event_info(event: Dict, index: int, total: int) -> None:
    """Отображает информацию о турнире"""
    print(f"\n{'='*60}")
    print(f"ТУРНИР {index}/{total}")
    print(f"{'='*60}")
    
    # Основная информация
    name = event.get('name', 'Без названия')
    date_str = event.get('date', '')
    event_id = event.get('id', 'N/A')
    
    print(f"🏆 Название: {name}")
    print(f"🆔 ID: {event_id}")
    
    if date_str:
        event_date = parse_espn_date(date_str)
        date_formatted = event_date.strftime("%d.%m.%Y %H:%M UTC")
        print(f"📅 Дата: {date_formatted}")
    
    # Дополнительная информация
    season = event.get('season', {})
    if season:
        year = season.get('year', 'N/A')
        print(f"📊 Год: {year}")
    
    # Статус
    status = event.get('status', {})
    status_type = status.get('type', {})
    status_name = status_type.get('name', 'unknown')
    print(f"📈 Статус: {status_name}")
    
    # Место проведения если есть
    competitions = event.get('competitions', [])
    if competitions:
        venue = competitions[0].get('venue', {})
        if venue:
            venue_name = venue.get('fullName', '')
            if venue_name:
                print(f"📍 Место: {venue_name}")
    
    # Ссылка если есть
    links = event.get('links', [])
    for link in links[:1]:  # Первая ссылка
        if link.get('rel', '') == ['summary']:
            print(f"🔗 Ссылка: {link.get('href', '')[:50]}...")


def display_all_fights(fights: List[Dict]) -> None:
    """Отображает ВСЕ бои турнира"""
    if not fights:
        print("\n❌ В этом турнире нет данных о боях")
        return
    
    print(f"\n🥊 КАРД ТУРНИРА ({len(fights)} боев):")
    print(f"{'-'*60}")
    
    for fight in fights:
        num = fight['number']
        f1 = fight['fighter1']
        f2 = fight['fighter2']
        rec1 = f" ({fight['fighter1_record']})" if fight['fighter1_record'] else ""
        rec2 = f" ({fight['fighter2_record']})" if fight['fighter2_record'] else ""
        status = fight['status']
        
        # Статус боя
        status_icon = "⏳"
        if status.lower() == 'finished':
            status_icon = "🏁"
        elif 'cancel' in status.lower():
            status_icon = "❌"
        
        print(f"{status_icon} {num}. {f1}{rec1} vs {f2}{rec2}")
    
    print(f"{'-'*60}")


async def main():
    """Основная функция"""
    print("🔍 UFC TOURNAMENT CHECKER - ПРОВЕРКА РЕАЛЬНЫХ ТУРНИРОВ")
    print("Получаем данные напрямую с ESPN API")
    print("=" * 60)
    
    # 1. Получаем турниры
    print("\n📡 Подключаемся к ESPN API...")
    events = await fetch_upcoming_events()
    
    if not events:
        print("❌ Не удалось получить турниры")
        return
    
    # 2. Отображаем список турниров
    print(f"\n📋 ДОСТУПНЫЕ ТУРНИРЫ ({len(events)}):")
    for i, event in enumerate(events, 1):
        name = event.get('name', 'Без названия')[:70]
        date_str = event.get('date', '')
        
        if date_str:
            event_date = parse_espn_date(date_str)
            date_short = event_date.strftime("%d.%m %H:%M")
        else:
            date_short = "дата неизвестна"
        
        print(f"{i:2}. {name:<70} | {date_short}")
    
    # 3. Выбор турнира
    print(f"\n{'='*60}")
    try:
        choice = input("Введите номер турнира для просмотра карда (0 для выхода): ").strip()
        
        if choice == '0':
            print("👋 Выход")
            return
        
        choice_num = int(choice)
        if choice_num < 1 or choice_num > len(events):
            print(f"❌ Неверный номер. Должен быть от 1 до {len(events)}")
            return
        
        selected_event = events[choice_num - 1]
        
    except ValueError:
        print("❌ Введите число!")
        return
    
    # 4. Показываем информацию о выбранном турнире
    print("\n" + "="*60)
    print("📊 ИНФОРМАЦИЯ О ТУРНИРЕ")
    print("="*60)
    display_event_info(selected_event, choice_num, len(events))
    
    # 5. Показываем ВСЕ бои
    fights = get_event_fights(selected_event)
    display_all_fights(fights)
    
    # 6. Спрашиваем, что делать дальше
    print(f"\n{'='*60}")
    print("Что дальше?")
    print("1. Вернуться к списку турниров")
    print("2. Выбрать другой турнир (по номеру)")
    print("3. Выход")
    
    try:
        next_action = input("Ваш выбор (1-3): ").strip()
        
        if next_action == '1':
            # Рекурсивный вызов для возврата
            await main()
        elif next_action == '2':
            # Повторный выбор
            print("\n" + "="*60)
            for i, event in enumerate(events, 1):
                name = event.get('name', 'Без названия')[:50]
                print(f"{i:2}. {name}")
            
            try:
                new_choice = int(input("\nВведите номер турнира: ").strip())
                if 1 <= new_choice <= len(events):
                    selected_event = events[new_choice - 1]
                    display_event_info(selected_event, new_choice, len(events))
                    fights = get_event_fights(selected_event)
                    display_all_fights(fights)
                else:
                    print("❌ Неверный номер")
            except ValueError:
                print("❌ Введите число!")
        else:
            print("👋 Выход")
    
    except KeyboardInterrupt:
        print("\n👋 Прервано пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Программа завершена")