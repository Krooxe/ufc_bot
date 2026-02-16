"""
Database Utils - Реэкспорт всех функций из services/
Для обратной совместимости со старым кодом

Этот файл больше не содержит логику - только импорты!
Вся логика перенесена в services/
"""

# Импортируем всё из services
from services.session import get_session
from utils.date_utils import parse_iso_date  # поменяли путь
from services.event_service import *
from services.fight_service import *
from services.user_service import *
from services.bet_service import *
from services.results_service import *
from services.settings_service import *

# Всё! Весь код теперь в services/
