"""
UFC API - Реэкспорт всех функций из api/
Для обратной совместимости со старым кодом

Этот файл больше не содержит логику - только импорты!
Вся логика перенесена в api/
"""

# Импортируем всё из api
from api.events import *
from api.fights import *
from api.results import *
from api.test_data import *

# Всё! Весь код теперь в api/
