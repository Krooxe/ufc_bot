"""
Создание турнира вручную через консоль
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_manual_event():
    """Создает турнир вручную"""
    # Создаем сессию
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        print("🎯 СОЗДАНИЕ ТУРНИРА ВРУЧНУЮ")
        print("=" * 50)
        
        # 1. Создаем событие
        event_title = "UFC Fight Night: Bautista vs. Oliveira"
        event_short = "UFC Fight Night"
        
        # Дата через 7 дней
        event_date = datetime.now(timezone.utc) + timedelta(days=7)
        
        from database import Event
        event = Event(
            ufc_api_id=None,  # Нет API ID, так как создаем вручную
            title=event_title,
            short_title=event_short,
            year=event_date.year,
            date_utc=event_date,
            date_msk=event_date,
            status="draft"
        )
        
        session.add(event)
        await session.flush()  # Получаем ID
        
        print(f"✅ Турнир создан: {event.title}")
        print(f"   ID: {event.id}")
        print(f"   Дата: {event_date.strftime('%d.%m.%Y %H:%M UTC')}")
        print(f"   Статус: {event.status}")
        
        # 2. Создаем бои (в обратном порядке!)
        from database import Fight
        
        # Список боев в правильном порядке (главный бой первый)
        fights_list = [
            "Mario Bautista vs Vinicius Oliveira",
            "Kyoji Horiguchi vs Amir Albazi", 
            "Rizvan Kuniev vs Jailton Almeida",
            "Michal Oleksiejczuk vs Marc-Andre Barriault",
            "Farid Basharat vs Jean Matsumoto",
            "Dustin Jacoby vs Julius Walker",
            "Alex Morono vs Daniil Donchenko",
            "Niko Price vs Nikolay Veretennikov",
            "Bruna Brasil vs Ketlen Souza",
            "Said Nurmagomedov vs Javid Basharat",
            "Wang Cong vs Eduarda Moura",
            "Muin Gafurov vs Jakub Wikłacz",
            "Priscila Cachoeira vs Klaudia Syguła"
        ]
        
        print(f"\n🥊 СОЗДАНИЕ БОЕВ ({len(fights_list)}):")
        print("-" * 50)
        
        for i, fight_str in enumerate(fights_list, 1):
            fighter1, fighter2 = fight_str.split(" vs ")
            
            fight = Fight(
                event_id=event.id,
                fight_order=i,  # i=1 - главный бой
                fighter1_name=fighter1.strip(),
                fighter2_name=fighter2.strip(),
                odds1=None,
                odds2=None,
                winner=None
            )
            session.add(fight)
            print(f"{i:2}. {fighter1:30} vs {fighter2}")
        
        await session.commit()
        
        print(f"\n✅ ГОТОВО!")
        print(f"Турнир '{event_title}' создан с {len(fights_list)} боями")
        print(f"ID турнира: {event.id}")
        print("\n📋 Дальнейшие действия:")
        print("1. Зайдите в админку бота")
        print("2. Нажмите '📥 Ввести кэфы'")
        print("3. Выберите ваш турнир")
        print("4. Введите коэффициенты")
        print("5. Сделайте ставки!")
        
        return event.id

async def main():
    """Основная функция"""
    try:
        event_id = await create_manual_event()
        
        # Проверяем что создалось
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            from database import Event, Fight
            from sqlalchemy import select
            
            # Проверяем турнир
            event_result = await session.execute(
                select(Event).where(Event.id == event_id)
            )
            event = event_result.scalar_one_or_none()
            
            if event:
                print(f"\n🔍 ПРОВЕРКА В БАЗЕ:")
                print(f"Турнир: {event.title}")
                print(f"Статус: {event.status}")
                
                # Проверяем бои
                fights_result = await session.execute(
                    select(Fight).where(Fight.event_id == event_id).order_by(Fight.fight_order)
                )
                fights = fights_result.scalars().all()
                print(f"Боев в базе: {len(fights)}")
                
                print("\n📊 Первые 3 боя в базе:")
                for fight in fights[:3]:
                    print(f"  Бой {fight.fight_order}: {fight.fighter1_name} vs {fight.fighter2_name}")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())