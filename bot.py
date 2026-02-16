"""
UFC Betting Bot - Главный файл
Telegram бот для ставок на турниры UFC

Точка входа приложения. Собирает все роутеры и запускает бота.
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database import create_tables

# Импортируем все роутеры
from handlers import commands, menu, archive, announcements, admin, odds_input
from handlers.bets import router as bets_router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота"""
    
    # Создаём таблицы в БД
    logger.info("Создание таблиц в базе данных...")
    await create_tables()
    
    # Инициализируем бота и диспетчер
    logger.info("Инициализация бота...")
    bot = Bot(token=config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Регистрируем роутеры в правильном порядке
    logger.info("Регистрация роутеров...")
    
    # 1. Команды (приоритет - самый высокий)
    dp.include_router(commands.router)
    
    # 2. Главное меню
    dp.include_router(menu.router)
    
    # 3. Архив и рейтинг
    dp.include_router(archive.router)
    
    # 4. Модуль ставок (включает все подроутеры)
    dp.include_router(bets_router)
    
    # 5. Объявления (требует bot instance)
    from handlers.announcements import set_bot
    set_bot(bot)
    dp.include_router(announcements.router)
    
    # 6. Админ-панель
    dp.include_router(admin.router)
    
    # 7. Ввод коэффициентов (с FSM состояниями)
    dp.include_router(odds_input.router)
    
    # Информация о запуске
    logger.info("=" * 50)
    logger.info("🚀 UFC Betting Bot запущен!")
    logger.info(f"🤖 Bot: @{(await bot.get_me()).username}")
    logger.info(f"👤 Admin ID: {config.ADMIN_ID}")
    logger.info(f"🗄️  Database: {config.DB_NAME}")
    logger.info(f"🔧 Debug mode: {config.DEBUG_MODE}")
    logger.info("=" * 50)
    
    # Запускаем polling
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
