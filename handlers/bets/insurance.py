"""
Выбор страховочной ставки
Шаг 3: Выбрать 1 бой для страховки (на случай отмены одного из основных)
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.states import temp_event_data

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data.startswith("select_insurance:"))
async def process_select_insurance(callback: CallbackQuery):
    """Выбор страховочного боя"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        betting_data = temp_event_data.get('betting_data', {}).get(user_id)
        
        if not betting_data:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            return
        
        await callback.answer()
        
        from db_utils import get_session, get_event_by_id
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            
            if not event:
                return
            
            # Получаем бои, которые НЕ выбраны как основные
            all_fights = betting_data['fights']
            selected_main = betting_data['selected_main_fights']
            
            available_fights = [f for f in all_fights if f.id not in selected_main]
            available_fights.sort(key=lambda f: f.fight_order)
            
            text = (
                f"🎯 <b>Сделать ставки: Шаг 3 из 4</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
                f"<b>🛡️ Выберите страховочную ставку:</b>\n\n"
                f"<i>Если один из ваших основных боёв будет отменён, "
                f"вместо него будет использована страховочная ставка.</i>\n\n"
                f"<b>Доступные бои для страховки:</b>\n"
            )
            
            for fight in available_fights:
                odds1 = f"{fight.odds1:.2f}" if fight.odds1 else "?"
                odds2 = f"{fight.odds2:.2f}" if fight.odds2 else "?"
                text += f"• Бой {fight.fight_order}: {fight.fighter1_name} ({odds1}) vs {fight.fighter2_name} ({odds2})\n"
            
            # Кнопки выбора боя
            buttons = []
            for fight in available_fights:
                btn_text = f"Бой {fight.fight_order}: {fight.fighter1_name} vs {fight.fighter2_name}"
                buttons.append([InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"choose_insurance_winner:{event_id}:{fight.id}"
                )])
            
            buttons.append([
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"confirm_main:{event_id}")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в select_insurance: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("choose_insurance_winner:"))
async def process_choose_insurance_winner(callback: CallbackQuery):
    """Выбор победителя в страховочном бою"""
    try:
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_id = int(parts[2])
        user_id = callback.from_user.id
        
        betting_data = temp_event_data.get('betting_data', {}).get(user_id)
        
        if not betting_data:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            return
        
        # Находим бой
        fights_dict = {f.id: f for f in betting_data['fights']}
        fight = fights_dict.get(fight_id)
        
        if not fight:
            await callback.answer("❌ Бой не найден", show_alert=True)
            return
        
        await callback.answer()
        
        # Показываем выбор победителя
        odds1 = f"{fight.odds1:.2f}" if fight.odds1 else "?"
        odds2 = f"{fight.odds2:.2f}" if fight.odds2 else "?"
        
        text = (
            f"🛡️ <b>Страховочная ставка - Бой {fight.fight_order}</b>\n\n"
            f"<b>{fight.fighter1_name}</b> (коэф: {odds1})\n"
            f"vs\n"
            f"<b>{fight.fighter2_name}</b> (коэф: {odds2})\n\n"
            f"<b>Выберите победителя:</b>"
        )
        
        buttons = [
            [InlineKeyboardButton(
                text=f"{fight.fighter1_name} ({odds1})",
                callback_data=f"set_insurance:{event_id}:{fight_id}:1"
            )],
            [InlineKeyboardButton(
                text=f"{fight.fighter2_name} ({odds2})",
                callback_data=f"set_insurance:{event_id}:{fight_id}:2"
            )],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_insurance_select:{event_id}")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в choose_insurance_winner: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("set_insurance:"))
async def process_set_insurance(callback: CallbackQuery):
    """Установка страховочной ставки"""
    try:
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_id = int(parts[2])
        chosen_fighter = int(parts[3])
        user_id = callback.from_user.id
        
        betting_data = temp_event_data.get('betting_data', {}).get(user_id)
        
        if not betting_data:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            return
        
        # Сохраняем страховку
        betting_data['insurance_fight_id'] = fight_id
        betting_data['insurance_winner'] = chosen_fighter
        
        # Вместо изменения callback.data, просто вызываем нужную функцию напрямую
        from .save import show_final_confirmation
        
        # Создаём новый callback_data для передачи
        fake_callback = callback
        # Не изменяем callback.data, а передаём event_id параметром
        
        await show_final_confirmation(callback, event_id)  # Передаём event_id отдельно
        
    except Exception as e:
        logger.error(f"Ошибка в set_insurance: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("back_to_insurance_select:"))
async def process_back_to_insurance_select(callback: CallbackQuery):
    """Возврат к выбору страховочного боя"""
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer()
        
        callback.data = f"select_insurance:{event_id}"
        await process_select_insurance(callback)
        
    except Exception as e:
        logger.error(f"Ошибка в back_to_insurance_select: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)
