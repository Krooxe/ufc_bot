import asyncio
import logging
from database import async_session
from ufc_api import get_test_ppv_event, get_event_fights_from_espn
from db_utils import (
    create_event_from_api,
    get_or_create_user,
    get_user_balance,
    open_event_for_bets,
    update_fight_odds_batch,
    get_open_event_with_fights
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

async def main():
    async with async_session() as session:
        print("🔹 Создание тестового турнира")
        event_data = get_test_ppv_event()
        fights_data = get_event_fights_from_espn(event_data)
        event = await create_event_from_api(session, event_data, fights_data)
        if event:
            print(f"✅ Турнир создан: {event.title} (ID: {event.id})")
        else:
            print("❌ Ошибка создания турнира")
            return

        print("\n🔹 Создание тестового пользователя")
        user = await get_or_create_user(session, user_id=123456, username="tester", full_name="Тест Юзер")
        balance = await get_user_balance(session, user.user_id)
        print(f"✅ Пользователь создан: {user.username}, баланс: {balance}")

        print("\n🔹 Открытие турнира для ставок")
        await open_event_for_bets(session, event.id)
        print(f"✅ Турнир {event.title} открыт для ставок")

        print("\n🔹 Обновление коэффициентов для боев")
        open_event = await get_open_event_with_fights(session)
        odds_list = [(fight.id, 1.5, 2.5) for fight in open_event['fights']]
        await update_fight_odds_batch(session, event.id, odds_list)
        print("✅ Коэффициенты обновлены")

        print("\n🔹 Проверка открытого турнира с боями")
        open_event = await get_open_event_with_fights(session)
        if open_event:
            print(f"Турнир: {open_event['event'].title}")
            for fight in open_event['fights']:
                print(f"Бой: {fight.fighter1_name} vs {fight.fighter2_name} | Коэфф: {fight.odds1}/{fight.odds2}")

asyncio.run(main())
