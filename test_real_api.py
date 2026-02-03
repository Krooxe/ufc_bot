import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ufc_api import fetch_upcoming_events, get_next_ppv_event, parse_espn_date

async def test_real_api():
    print("🔍 Тестирование РЕАЛЬНОГО ESPN API...")
    print("(DEBUG_MODE должен быть False в config.py)")
    print()
    
    # 1. Получаем реальные данные
    events = await fetch_upcoming_events()
    
    if not events:
        print("❌ Не удалось получить события от ESPN API")
        print("   Возможные причины:")
        print("   - Нет интернета")
        print("   - ESPN API изменился")
        print("   - Блокировка запросов")
        return
    
    print(f"✅ Получено событий: {len(events)}")
    
    # 2. Покажем все события что получили
    print("\n📅 Все предстоящие события от ESPN:")
    for i, event in enumerate(events[:10], 1):  # Покажем первые 10
        date_str = event.get('date', 'N/A')[:19]  # Обрезаем до даты
        print(f"  {i}. {event.get('name', 'N/A')[:50]}... | {date_str}")
    
    # 3. Ищем PPV
    print("\n🔎 Ищем PPV турниры...")
    next_ppv = get_next_ppv_event(events)
    
    if next_ppv:
        print(f"🎉 Найден PPV турнир!")
        print(f"   Название: {next_ppv.get('name', 'N/A')}")
        print(f"   Дата: {next_ppv.get('date', 'N/A')}")
        print(f"   ID: {next_ppv.get('id', 'N/A')}")
        
        # Проверяем фильтрацию
        name = next_ppv.get('name', '').lower()
        if 'fight night' in name:
            print("   ⚠️  Это Fight Night, а не PPV!")
        elif 'ufc' in name and any(char.isdigit() for char in name):
            print("   ✅ Похож на номерной PPV турнир")
        else:
            print("   🤔 Непонятный формат названия")
    else:
        print("❌ PPV турниры не найдены")
        print("   Возможно:")
        print("   - Сейчас нет предстоящих PPV")
        print("   - ESPN возвращает только ближайшие Fight Night")
        print("   - Нужно настроить фильтрацию по-другому")

if __name__ == "__main__":
    asyncio.run(test_real_api())