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
    
    welcome_text = (
        f"👊 Привет, {user.first_name}!\n\n"
        f"Я бот для ставок на UFC. Твой ID: {user.id}\n"
        "Следи за турнирами, делай ставки и соревнуйся с друзьями!\n\n"
        "⬇️ Используй меню ниже:"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_menu())
    
    # СОЗДАЁМ/ПОЛУЧАЕМ ПОЛЬЗОВАТЕЛЯ В БАЗЕ
    try:
        from db_utils import get_session, get_or_create_user
        
        async with get_session() as session:
            db_user = await get_or_create_user(
                session,
                user.id,
                user.username,
                user.full_name
            )
            logger.info(f"Пользователь в БД: {db_user.user_id} - {db_user.username}")
    except Exception as e:
        logger.error(f"Ошибка создания пользователя: {e}")


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда /admin - только для админа"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ У вас нет прав доступа к админ-панели.")
        return
    
    text = (
        f"⚙️ <b>Админ-панель</b>\n\n"
        f"Привет, админ {message.from_user.first_name}!\n"
        f"ID: {message.from_user.id}\n\n"
        f"Выберите действие:"
    )
    
    await message.answer(text, reply_markup=get_admin_menu(), parse_mode="HTML")
    logger.info(f"Админ вошел: {message.from_user.id}")


@router.message(Command("cleardb"))
async def cmd_clear_db(message: Message):
    """Полная очистка ТЕСТОВОЙ БД (только админ)"""
    if message.from_user.id != config.ADMIN_ID:
        return
    
    await message.answer(f"🗑️ Очищаю ТЕСТОВУЮ базу данных ({config.DB_NAME})...")
    
    from database import engine, Base
    
    async def clear_all():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    
    await clear_all()
    await message.answer(f"✅ Тестовая база данных полностью очищена и пересоздана")
