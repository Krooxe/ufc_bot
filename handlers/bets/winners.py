"""
Выбор победителей в выбранных боях
Шаг 2: Для каждого из 5 выбранных боёв указать победителя
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.keyboards import get_back_button
from utils.states import temp_event_data

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data.startswith("confirm_main:"))
async def process_confirm_main(callback: CallbackQuery):
    """Подтверждение выбора боёв и переход к выбору победителей"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        betting_data = temp_event_data.get('betting_data', {}).get(user_id)
        
        if not betting_data:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            return
        
        selected_fights = betting_data['selected_main_fights']
        
        if len(selected_fights) != 5:
            await callback.answer(f"⚠️ Нужно выбрать ровно 5 боев! Сейчас выбрано: {len(selected_fights)}", show_alert=True)
            return
        
        betting_data['step'] = 'choose_winners'
        await callback.answer()
        
        # Показываем выбор победителей
        from db_utils import get_session, get_event_by_id
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            
            if not event:
                await callback.answer("❌ Турнир не найден", show_alert=True)
                return
            
            # Формируем текст
            fights = betting_data['fights']
            fights_dict = {f.id: f for f in fights}
            
            # Сортируем выбранные бои по fight_order
            selected_fights_sorted = []
            for fight_id in selected_fights:
                fight = fights_dict.get(fight_id)
                if fight:
                    selected_fights_sorted.append(fight)
            
            selected_fights_sorted.sort(key=lambda f: f.fight_order)
            
            text = (
                f"🎯 <b>Сделать ставки: Шаг 2 из 4</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
                f"<b>Выберите победителей в каждом бою:</b>\n\n"
            )
            
            selected_winners = betting_data.get('selected_winners', {})
            
            for fight in selected_fights_sorted:
                odds1 = f"{fight.odds1:.2f}" if fight.odds1 else "?"
                odds2 = f"{fight.odds2:.2f}" if fight.odds2 else "?"
                
                winner_chosen = selected_winners.get(fight.id)
                if winner_chosen == 1:
                    status = f"✅ {fight.fighter1_name}"
                elif winner_chosen == 2:
                    status = f"✅ {fight.fighter2_name}"
                else:
                    status = "❓ Не выбрано"
                
                text += f"<b>Бой {fight.fight_order}:</b> {fight.fighter1_name} ({odds1}) vs {fight.fighter2_name} ({odds2})\n"
                text += f"<i>Выбор:</i> {status}\n\n"
            
            text += f"<b>Выбрано победителей:</b> {len(selected_winners)}/5\n"
            text += "<i>Нажмите на бой, чтобы выбрать победителя</i>"
            
            # Кнопки выбора боёв
            buttons = []
            for fight in selected_fights_sorted:
                winner_chosen = selected_winners.get(fight.id)
                if winner_chosen:
                    btn_text = f"✅ Бой {fight.fight_order}"
                else:
                    btn_text = f"Бой {fight.fight_order}"
                
                buttons.append([InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"choose_winner:{event_id}:{fight.id}"
                )])
            
            # Кнопки навигации
            control_row = []
            if len(selected_winners) == 5:
                control_row.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"select_insurance:{event_id}"))
            control_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_fight:{event_id}"))
            buttons.append(control_row)
            
            buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_current")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в confirm_main: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )


@router.callback_query(lambda c: c.data.startswith("choose_winner:"))
async def process_choose_winner(callback: CallbackQuery):
    """Показ меню выбора победителя конкретного боя"""
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
        
        current_choice = betting_data.get('selected_winners', {}).get(fight_id)
        
        text = (
            f"🥊 <b>Бой {fight.fight_order}</b>\n\n"
            f"<b>{fight.fighter1_name}</b> (коэф: {odds1})\n"
            f"vs\n"
            f"<b>{fight.fighter2_name}</b> (коэф: {odds2})\n\n"
            f"<b>Выберите победителя:</b>\n"
        )
        
        if current_choice:
            winner_name = fight.fighter1_name if current_choice == 1 else fight.fighter2_name
            text += f"<i>Текущий выбор: {winner_name}</i>"
        
        buttons = [
            [InlineKeyboardButton(
                text=f"{'✅ ' if current_choice == 1 else ''}{fight.fighter1_name} ({odds1})",
                callback_data=f"set_winner:{event_id}:{fight_id}:1"
            )],
            [InlineKeyboardButton(
                text=f"{'✅ ' if current_choice == 2 else ''}{fight.fighter2_name} ({odds2})",
                callback_data=f"set_winner:{event_id}:{fight_id}:2"
            )],
            [InlineKeyboardButton(text="⬅️ Назад к выбору боёв", callback_data=f"back_to_winners:{event_id}")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в choose_winner: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("set_winner:"))
async def process_set_winner(callback: CallbackQuery):
    """Установка победителя для боя"""
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
        
        # Сохраняем выбор
        if 'selected_winners' not in betting_data:
            betting_data['selected_winners'] = {}
        
        betting_data['selected_winners'][fight_id] = chosen_fighter
        
        # Находим имя бойца
        fights_dict = {f.id: f for f in betting_data['fights']}
        fight = fights_dict.get(fight_id)
        winner_name = fight.fighter1_name if chosen_fighter == 1 else fight.fighter2_name
        
        await callback.answer(f"✅ Выбран победитель: {winner_name}")
        
        # Возвращаемся к списку боёв
        await process_confirm_main(callback)
        
    except Exception as e:
        logger.error(f"Ошибка в set_winner: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("back_to_winners:"))
async def process_back_to_winners(callback: CallbackQuery):
    """Возврат к списку боёв для выбора победителей"""
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer()
        
        # Создаём фейковый callback с нужными данными
        callback.data = f"confirm_main:{event_id}"
        await process_confirm_main(callback)
        
    except Exception as e:
        logger.error(f"Ошибка в back_to_winners: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)
