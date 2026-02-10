"""
manual_event_creator.py - Создает черновик турнира из второго прошедшего события UFC
Парсит правильный порядок бойцов, НЕ добавляет победителей
"""
import asyncio
import re
import aiohttp
from bs4 import BeautifulSoup
import sys
import os
from datetime import datetime, timezone
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EVENTS_URL = "http://ufcstats.com/statistics/events/completed"


async def get_second_event(session):
    """Получает второй турнир с ufcstats.com"""
    async with session.get(EVENTS_URL) as response:
        soup = BeautifulSoup(await response.text(), "html.parser")

        event_links = soup.find_all("a", href=re.compile("event-details"))
        if len(event_links) < 2:
            raise Exception("Найдено меньше двух турниров")

        link = event_links[1]
        event_url = link["href"]
        event_title = link.text.strip()
        
        # Парсим дату
        parent_td = link.find_parent('td')
        event_date = datetime.now(timezone.utc)  # по умолчанию
        
        if parent_td:
            date_match = re.search(
                r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', 
                parent_td.text
            )
            if date_match:
                event_date = datetime.strptime(date_match.group(), "%B %d, %Y").replace(
                    tzinfo=timezone.utc, hour=18
                )
        
        return event_url, event_title, event_date


async def get_fight_links(session, event_url):
    """Получает все ссылки на бои события"""
    async with session.get(event_url) as response:
        soup = BeautifulSoup(await response.text(), "html.parser")

        return [
            a["href"]
            for a in soup.find_all("a", class_="b-flag")
            if "fight-details" in a.get("href", "")
        ]


async def parse_fight_names(session, fight_url):
    """Парсит ТОЛЬКО имена бойцов (без победителя)"""
    async with session.get(fight_url) as response:
        soup = BeautifulSoup(await response.text(), "html.parser")

        # Имена бойцов (правильный порядок с детальной страницы)
        fighters = [
            a.text.strip()
            for a in soup.find_all("a", class_="b-fight-details__person-link")
        ]

        if len(fighters) < 2:
            raise Exception("Не удалось получить обоих бойцов")

        # ТОЛЬКО имена, без победителя
        return fighters[0], fighters[1]


async def create_draft_event():
    """Создает черновик турнира в БД (без победителей)"""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db_session:
        print("🎯 СОЗДАНИЕ ЧЕРНОВИКА ТУРНИРА ИЗ UFCSTATS.COM")
        print("=" * 60)
        
        async with aiohttp.ClientSession() as http_session:
            # 1. Получаем данные второго турнира
            event_url, event_title, event_date = await get_second_event(http_session)
            
            print(f"📥 Турнир: {event_title}")
            print(f"📅 Дата: {event_date.strftime('%d.%m.%Y %H:%M UTC')}")
            
            # 2. Получаем список боев
            fight_links = await get_fight_links(http_session, event_url)
            print(f"\n🥊 Найдено {len(fight_links)} боев")
            print("-" * 60)
            
            # 3. Парсим каждый бой (ТОЛЬКО имена, без победителей)
            fights_list = []
            for i, fight_url in enumerate(fight_links, 1):
                try:
                    fighter1, fighter2 = await parse_fight_names(http_session, fight_url)
                    fights_list.append((fighter1, fighter2))
                    print(f"{i:2}. {fighter1:30} vs {fighter2}")
                except Exception as e:
                    print(f"{i:2}. ⚠️ Ошибка: {e}")
                    # Добавляем заглушку
                    fights_list.append((f"Fighter_{i}_A", f"Fighter_{i}_B"))
            
            print("-" * 60)
            
            # 4. Создаем событие в БД (статус: draft)
            from database import Event
            event = Event(
                ufc_api_id=None,
                title=event_title,
                short_title=event_title[:50],
                year=event_date.year,
                date_utc=event_date,
                date_msk=event_date,
                status="draft"  # ЧЕРНОВИК!
            )
            
            db_session.add(event)
            await db_session.flush()  # Получаем ID
            
            # 5. Создаем бои в БД (без победителей!)
            from database import Fight
            created_fights = 0
            
            for i, (fighter1, fighter2) in enumerate(fights_list, 1):
                fight = Fight(
                    event_id=event.id,
                    fight_order=i,
                    fighter1_name=fighter1,
                    fighter2_name=fighter2,
                    odds1=None,    # Пусто для ввода через админку
                    odds2=None,    # Пусто для ввода через админку
                    winner=None    # НЕТ ПОБЕДИТЕЛЯ в черновике!
                )
                db_session.add(fight)
                created_fights += 1
            
            await db_session.commit()
            
            print(f"\n✅ ЧЕРНОВИК ТУРНИРА СОЗДАН")
            print(f"   Название: {event_title}")
            print(f"   Создано боев: {created_fights}")
            
            return event.id


async def main():
    try:
        event_id = await create_draft_event()
        
        
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())