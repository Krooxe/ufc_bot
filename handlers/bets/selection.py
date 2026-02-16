"""
Выбор основных боёв для ставок
Шаг 1: Выбрать 5 боёв из списка
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.keyboards import get_back_button
from utils.states import temp_event_data
from handlers.menu import update_fight_selection_message

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data.startswith("make_bets:"))
async def process_make_bets_start(callback: CallbackQuery):
    """Начало процесса ставок - выбор 5 основных боев"""
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer()
        
        from db_utils import get_session, get_fights_for_event, get_event_by_id
        
        async with get_session() as session:
            # Получаем турнир и бои
            event = await get_event_by_id(session, event_id)
            fights = await get_fights_for_event(session, event_id)
            
            if not event or not fights:
                await callback.message.edit_text(
                    "❌ Ошибка: турнир не найден",
                    reply_markup=get_back_button()
                )
                return
            
            # Сохраняем данные для пользователя
            user_id = callback.from_user.id
            if 'betting_data' not in temp_event_data:
                temp_event_data['betting_data'] = {}
            
            temp_event_data['betting_data'][user_id] = {
                'event_id': event_id,
                'fights': fights,
                'selected_main_fights': [],  # ID выбранных основных боев
                'selected_winners': {},  # {fight_id: chosen_fighter}
                'insurance_fight_id': None,
                'insurance_winner': None,
                'step': 'choose_main'  # Текущий шаг
            }
            
            # Формируем сообщение с выбором боев
            fights_text = ""
            for i, fight in enumerate(fights, 1):
                odds1 = f"{fight.odds1:.2f}" if fight.odds1 else "?"
                odds2 = f"{fight.odds2:.2f}" if fight.odds2 else "?"
                fights_text += f"{i}. {fight.fighter1_name} (<b>{odds1}</b>) vs {fight.fighter2_name} (<b>{odds2}</b>)\n"
            
            text = (
                f"🎯 <b>Сделать ставки: Шаг 1 из 4</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
                f"<b>Выберите 5 основных боев:</b>\n"
                f"(нажмите на номера боев, которые хотите выбрать)\n\n"
                f"{fights_text}\n"
                f"<b>Выбрано:</b> 0/5\n"
                f"<i>Выбирайте бои, на исход которых хотите поставить.</i>"
            )
            
            # Создаём инлайн-кнопки для выбора боев
            buttons = []
            row = []
            for i, fight in enumerate(fights, 1):
                btn_text = f"{i}"
                callback_data = f"select_fight:{event_id}:{fight.id}"
                row.append(InlineKeyboardButton(text=btn_text, callback_data=callback_data))
                
                if len(row) == 3:  # 3 кнопки в ряд
                    buttons.append(row)
                    row = []
            
            if row:
                buttons.append(row)
            
            # Кнопки управления
            buttons.append([
                InlineKeyboardButton(text="🔄 Сбросить", callback_data=f"reset_main:{event_id}")
            ])
            buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_current")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в make_bets: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )


@router.callback_query(lambda c: c.data.startswith("select_fight:"))
async def process_select_fight(callback: CallbackQuery):
    """Выбор/отмена выбора боя"""
    try:
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_id = int(parts[2])
        user_id = callback.from_user.id
        
        betting_data = temp_event_data.get('betting_data', {}).get(user_id)
        
        if not betting_data:
            await callback.answer("❌ Ошибка: данные не найдены", show_alert=True)
            return
        
        selected = betting_data['selected_main_fights']
        
        # Переключаем выбор
        if fight_id in selected:
            selected.remove(fight_id)
            await callback.answer("✅ Бой убран из выбора")
        else:
            if len(selected) >= 5:
                await callback.answer("⚠️ Уже выбрано 5 боев! Сначала уберите один.", show_alert=True)
                return
            selected.append(fight_id)
            await callback.answer(f"✅ Выбрано боев: {len(selected)}/5")
        
        # Обновляем сообщение
        await update_fight_selection_message(callback.message, user_id, event_id)
        
    except Exception as e:
        logger.error(f"Ошибка в select_fight: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("reset_main:"))
async def process_reset_main(callback: CallbackQuery):
    """Сброс выбранных боев"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        betting_data = temp_event_data.get('betting_data', {}).get(user_id)
        
        if betting_data:
            betting_data['selected_main_fights'] = []
            betting_data['selected_winners'] = {}
            await callback.answer("🔄 Выбор сброшен")
            await update_fight_selection_message(callback.message, user_id, event_id)
        else:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка в reset_main: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("back_to_fight:"))
async def process_back_to_fight(callback: CallbackQuery):
    """Возврат к выбору боёв из выбора победителей"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        betting_data = temp_event_data.get('betting_data', {}).get(user_id)
        
        if betting_data:
            betting_data['step'] = 'choose_main'
            betting_data['selected_winners'] = {}  # Сбрасываем победителей
            await callback.answer()
            await update_fight_selection_message(callback.message, user_id, event_id)
        else:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка в back_to_fight: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)
