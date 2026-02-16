"""
Модуль обработчиков ставок
Betting flow: просмотр, выбор боёв, выбор победителей, страховка, сохранение
"""
from aiogram import Router

# Импортируем все роутеры из подмодулей
from .view import router as view_router
from .selection import router as selection_router
from .winners import router as winners_router
from .insurance import router as insurance_router
from .save import router as save_router

# Создаём главный роутер для ставок
router = Router()

# Подключаем все подроутеры
router.include_router(view_router)
router.include_router(selection_router)
router.include_router(winners_router)
router.include_router(insurance_router)
router.include_router(save_router)

__all__ = ['router']
