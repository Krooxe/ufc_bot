"""
FSM States для UFC Bot
Состояния для конечного автомата (Finite State Machine)
"""
from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_odds = State()  # Ожидание ввода коэффициентов
    waiting_for_results = State()  # Ожидание ввода результатов
    waiting_for_announcement = State()  # Ожидание текста объявления


# Глобальная переменная для хранения временных данных администратора
# TODO: в будущем заменить на Redis или другое хранилище
temp_event_data = {}
