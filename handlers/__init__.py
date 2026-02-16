"""
Модуль обработчиков UFC Betting Bot
Все роутеры для различных функций бота
"""

# Импортируем все модули, чтобы они были доступны
from . import commands
from . import menu
from . import archive
from . import announcements
from . import admin
from . import bets
from . import odds_input  # ← Новый модуль

__all__ = [
    'commands',
    'menu',
    'archive',
    'announcements',
    'admin',
    'bets',
    'odds_input',  # ← Новый модуль
]
