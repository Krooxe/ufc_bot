"""
Ввод коэффициентов для турнира
Простой интерфейс без лишних окон
"""
import logging
import re
from aiogram import Router
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal

import config
from utils.keyboards import get_admin_menu

logger = logging.getLogger(__name__)

router = Router()


class OddsInputStates(StatesGroup):
    """Состояния для ввода коэффициентов"""
    waiting_for_odds = State()


@router.callback_query(lambda c: c.data == "admin_add_odds")
async def start_odds_input(callback: CallbackQuery, state: FSMContext):
    """Начало ввода коэффициентов - сразу показываем бои"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.answer()
    
    try:
        from db_utils import get_session, get_open_or_draft_events, get_fights_for_event
        
        async with get_session() as session:
            # Получаем турниры, доступные для ввода коэффициентов (draft или open_for_bets)
            events = await get_open_or_draft_events(session)
            
            if not events:
                await callback.message.edit_text(
                    "❌ Нет турниров для ввода коэффициентов.\n\nСоздайте турнир сначала.",
                    reply_markup=get_admin_menu()
                )
                return
            
            # Берём первый доступный турнир
            event = events[0]
            fights = await get_fights_for_event(session, event.id)
            
            if not fights:
                await callback.message.edit_text(
                    "❌ В турнире нет боёв.",
                    reply_markup=get_admin_menu()
                )
                return
            
            # Сохраняем event_id в состоянии
            await state.update_data(event_id=event.id)
            await state.set_state(OddsInputStates.waiting_for_odds)
            
            # Формируем сообщение с боями
            text = (
                f"📥 <b>Ввод коэффициентов</b>\n\n"
                f"🏆 <b>{event.title}</b> (статус: {event.status})\n\n"
                f"<b>Список боёв:</b>\n"
            )
            
            for fight in fights:
                text += f"\n{fight.fight_order}. {fight.fighter1_name} vs {fight.fighter2_name}"
            
            text += (
                "\n\n<b>📝 Введите коэффициенты в формате:</b>\n"
                "<code>1. 1.45 2.75\n"
                "2. 1.80 2.05\n"
                "3. 1.65 2.25</code>\n\n"
                "<i>Каждый бой с новой строки: номер, коэф1, коэф2</i>"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_odds_input")]
            ])
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка start_odds_input: {e}", exc_info=True)
        await callback.message.edit_text(
            "❌ Ошибка загрузки турнира",
            reply_markup=get_admin_menu()
        )


@router.message(OddsInputStates.waiting_for_odds)
async def process_odds_input(message: Message, state: FSMContext):
    """Обработка введённых коэффициентов"""
    if message.from_user.id != config.ADMIN_ID:
        return
    
    try:
        # Получаем event_id из состояния
        data = await state.get_data()
        event_id = data.get('event_id')
        
        if not event_id:
            await message.answer("❌ Ошибка: турнир не найден")
            await state.clear()
            return
        
        # Парсим введённые коэффициенты
        text = message.text.strip()
        lines = text.split('\n')
        
        odds_data = {}  # {fight_order: (odds1, odds2)}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Парсим строку: "1. 1.45 2.75" или "1 1.45 2.75"
            match = re.match(r'(\d+)\.?\s+(\d+\.?\d*)\s+(\d+\.?\d*)', line)
            
            if match:
                fight_num = int(match.group(1))
                odds1 = float(match.group(2))
                odds2 = float(match.group(3))
                odds_data[fight_num] = (odds1, odds2)
        
        if not odds_data:
            await message.answer(
                "❌ Не удалось распознать коэффициенты.\n\n"
                "Убедитесь, что формат правильный:\n"
                "<code>1. 1.45 2.75\n2. 1.80 2.05</code>",
                parse_mode="HTML"
            )
            return
        
        # Сохраняем коэффициенты во временное хранилище
        await state.update_data(odds_data=odds_data)
        
        # Получаем бои и показываем предпросмотр
        from db_utils import get_session, get_event_by_id, get_fights_for_event
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            fights = await get_fights_for_event(session, event_id)
            
            # Формируем сообщение с предпросмотром
            text = (
                f"✅ <b>Предпросмотр коэффициентов</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
            )
            
            for fight in fights:
                if fight.fight_order in odds_data:
                    odds1, odds2 = odds_data[fight.fight_order]
                    text += f"\n{fight.fight_order}. {fight.fighter1_name} (<b>{odds1:.2f}</b>) vs {fight.fighter2_name} (<b>{odds2:.2f}</b>)"
                else:
                    text += f"\n{fight.fight_order}. {fight.fighter1_name} (❓) vs {fight.fighter2_name} (❓)"
            
            text += f"\n\n<b>Введено коэффициентов:</b> {len(odds_data)}/{len(fights)}"
            
            if len(odds_data) < len(fights):
                text += "\n\n⚠️ <i>Введены не все коэффициенты!</i>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💾 Сохранить", callback_data="save_odds")],
                [InlineKeyboardButton(text="✏️ Ввести заново", callback_data="admin_add_odds")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_odds_input")]
            ])
            
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка process_odds_input: {e}", exc_info=True)
        await message.answer("❌ Ошибка обработки коэффициентов")
        await state.clear()


@router.callback_query(lambda c: c.data == "save_odds")
async def save_odds(callback: CallbackQuery, state: FSMContext):
    """Сохранение коэффициентов в БД"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.answer("💾 Сохраняю коэффициенты...")
    
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        event_id = data.get('event_id')
        odds_data = data.get('odds_data', {})
        
        if not event_id or not odds_data:
            await callback.message.edit_text(
                "❌ Нет данных для сохранения",
                reply_markup=get_admin_menu()
            )
            await state.clear()
            return
        
        # Сохраняем коэффициенты
        from db_utils import get_session, get_fights_for_event
        from database import Fight
        
        async with get_session() as session:
            fights = await get_fights_for_event(session, event_id)
            
            updated_count = 0
            for fight in fights:
                if fight.fight_order in odds_data:
                    odds1, odds2 = odds_data[fight.fight_order]
                    fight.odds1 = Decimal(str(odds1))
                    fight.odds2 = Decimal(str(odds2))
                    updated_count += 1
            
            await session.commit()
            
            await callback.message.edit_text(
                f"✅ <b>Коэффициенты сохранены!</b>\n\n"
                f"Обновлено боёв: {updated_count}\n\n"
                f"Теперь можно открыть турнир для ставок.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔓 Открыть для ставок", callback_data=f"admin_open_betting:{event_id}")],
                    [InlineKeyboardButton(text="🏠 В админ-панель", callback_data="admin_status")]
                ]),
                parse_mode="HTML"
            )
            
            await state.clear()
            
    except Exception as e:
        logger.error(f"Ошибка save_odds: {e}", exc_info=True)
        await callback.message.edit_text(
            "❌ Ошибка сохранения коэффициентов",
            reply_markup=get_admin_menu()
        )
        await state.clear()


@router.callback_query(lambda c: c.data == "cancel_odds_input")
async def cancel_odds_input(callback: CallbackQuery, state: FSMContext):
    """Отмена ввода коэффициентов"""
    await state.clear()
    await callback.answer("Отменено")
    
    from utils.keyboards import get_admin_menu
    await callback.message.edit_text(
        "↩️ Возврат в админ-панель",
        reply_markup=get_admin_menu()
    )
