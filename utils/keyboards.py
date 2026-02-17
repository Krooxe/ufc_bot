"""
Клавиатуры для UFC Bot
Все inline-клавиатуры бота в одном месте
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu() -> InlineKeyboardMarkup:
    """Создает главное меню с inline-кнопками"""
    buttons = [
        [InlineKeyboardButton(text="🥊 Текущий турнир", callback_data="menu_current")],
        [InlineKeyboardButton(text="📈 Общий рейтинг", callback_data="menu_rating")],
        [InlineKeyboardButton(text="🏆 Архив", callback_data="menu_archive")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_button() -> InlineKeyboardMarkup:
    """Кнопка 'Назад' в главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back")]
    ])


def get_admin_menu() -> InlineKeyboardMarkup:
    """Меню админ-панели"""
    buttons = [
        [InlineKeyboardButton(text="➕ Новый PPV", callback_data="admin_new_ppv")],
        [InlineKeyboardButton(text="📥 Ввести кэфы", callback_data="admin_add_odds")],
        [InlineKeyboardButton(text="🏁 Закрыть турнир", callback_data="admin_close_event")],
        [InlineKeyboardButton(text="📢 Объявление", callback_data="admin_announce")],
        # [InlineKeyboardButton(text="ℹ️ Статус", callback_data="admin_status")],
        [InlineKeyboardButton(text="✖️ Выход", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
