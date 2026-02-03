import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db_utils import create_event_from_api, async_session
from ufc_api import get_test_ppv_event, get_event_fights_from_espn

async def test_create():
    print("1. Получаем тестовые данные...")
    event_data = get_test_ppv_event()
    fights_data = get_event_fights_from_espn(event_data)
    
    print(f"   Название: {event_data.get('name')}")
    print(f"   Боев: {len(fights_data)}")
    
    print("\n2. Пробуем создать в БД...")
    async with async_session() as session:
        try:
            event = await create_event_from_api(session, event_data, fights_data)
            if event:
                print(f"   ✅ УСПЕХ! Турнир создан:")
                print(f"      ID: {event.id}")
                print(f"      Название: {event.title}")
                print(f"      Статус: {event.status}")
            else:
                print("   ❌ create_event_from_api вернул None")
        except Exception as e:
            print(f"   ❌ ОШИБКА при создании: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_create())