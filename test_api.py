import aiohttp
import asyncio

async def test_url(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                print(f"{url} -> статус: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if data:
                        print(f"  Данные получены, объектов: {len(data) if isinstance(data, list) else 1}")
                        if isinstance(data, list) and len(data) > 0:
                            print(f"  Первый объект: {data[0].get('title', 'N/A')[:50]}...")
                    return True
                return False
    except Exception as e:
        print(f"{url} -> ошибка: {e}")
        return False

async def main():
    print("Тестирование доступных UFC API...\n")
    
    urls = [
        "http://ufc-data-api.ufc.com/api/v3/us/events",
        "http://ufc-data-api.ufc.com/api/v3/events",
        "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard",
        "https://raw.githubusercontent.com/valish/ufc-api/master/ufc.json",
    ]
    
    for url in urls:
        success = await test_url(url)
        if success:
            print(f"✅ {url} РАБОТАЕТ")
        else:
            print(f"❌ {url} НЕ РАБОТАЕТ")
        print()

if __name__ == "__main__":
    asyncio.run(main())