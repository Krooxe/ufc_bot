"""
Обработчики команд бота
/start, /admin, /cleardb
"""
import logging
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

import config
from utils.keyboards import get_main_menu, get_admin_menu

logger = logging.getLogger(__name__)

# Создаём роутер для команд
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработка команды /start"""
    user = message.from_user
    balance = 0  # значение по умолчанию
    
    # СОЗДАЁМ/ПОЛУЧАЕМ ПОЛЬЗОВАТЕЛЯ В БАЗЕ
    try:
        from db_utils import get_session, get_or_create_user, get_user_balance
        
        async with get_session() as session:
            # Создаём/получаем юзера
            db_user = await get_or_create_user(
                session,
                user.id,
                user.username,
                user.full_name
            )
            
            # Получаем баланс
            from services.user_service import get_user_balance
            balance = await get_user_balance(session, user.id)
            
            logger.info(f"Пользователь в БД: {db_user.user_id} - {db_user.username}")
    except Exception as e:
        logger.error(f"Ошибка создания пользователя: {e}")
    
    # Формируем новое приветствие
    welcome_text = (
        f"👊 Привет, {user.full_name}!\n\n"
        f"Я бот для ставок на UFC.\n"
        f"Следи за турнирами, делай ставки и соревнуйся с друзьями!\n\n"
        f"💰 Твой текущий результат: {balance} очков\n\n"
        f"⬇️ Используй меню ниже:"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_menu())


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда /admin - только для админа"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ У вас нет прав доступа к админ-панели.")
        return
    
    text = (
        f"⚙️ <b>Админ-панель</b>\n\n"
        f"Привет, админ {message.from_user.first_name}!\n\n"
        f"Выберите действие:"
    )
    
    await message.answer(text, reply_markup=get_admin_menu(), parse_mode="HTML")
    logger.info(f"Админ вошел: {message.from_user.id}")


@router.message(Command("cleardb"))
async def cmd_clear_db(message: Message):
    """Полная очистка базы данных (работает только в DEBUG_MODE)"""
    if message.from_user.id != config.ADMIN_ID:
        return
    
    # Защита от случайной очистки продакшн БД
    if not config.DEBUG_MODE:
        await message.answer(
            "❌ Команда cleardb доступна только в DEBUG_MODE!\n"
            "Для продакшн базы используйте ручное управление."
        )
        return
    
    await message.answer(f"🗑️ Очищаю базу данных ({config.DB_NAME})...")
    
    try:
        from database import engine, Base
        import os
        
        # Закрываем все соединения
        await engine.dispose()
        
        # Удаляем файл БД
        if os.path.exists(config.DB_NAME):
            os.remove(config.DB_NAME)
            await message.answer(f"✅ Файл {config.DB_NAME} удалён")
        
        # Создаём таблицы заново
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        await message.answer(f"✅ База данных полностью пересоздана")
        logger.info(f"БД {config.DB_NAME} очищена и пересоздана админом {message.from_user.id}")
            
    except Exception as e:
        logger.error(f"Ошибка cleardb: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")
