"""
Финальное сохранение ставок в базу данных
Шаг 4: Показать итоговую сводку и сохранить
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from decimal import Decimal

from utils.keyboards import get_back_button
from utils.states import temp_event_data

logger = logging.getLogger(__name__)

router = Router()


async def show_final_confirmation(callback: CallbackQuery, event_id: int = None):
    """Показывает финальное подтверждение перед сохранением"""
    try:
        if event_id is None:
            # Если event_id не передан, берём из callback.data
            event_id = int(callback.data.split(":")[1])
        
        user_id = callback.from_user.id
        # ... остальной код без изменений
        
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
            
            # Формируем итоговое сообщение
            fights_dict = {f.id: f for f in betting_data['fights']}
            selected_fights = betting_data['selected_main_fights']
            selected_winners = betting_data['selected_winners']
            insurance_id = betting_data.get('insurance_fight_id')
            insurance_winner = betting_data.get('insurance_winner')
            
            # Сортируем основные бои
            sorted_fights = []
            for fight_id in selected_fights:
                fight = fights_dict.get(fight_id)
                if fight:
                    sorted_fights.append(fight)
            sorted_fights.sort(key=lambda f: f.fight_order)
            
            text = (
                f"🎯 <b>Сделать ставки: Шаг 4 из 4</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
                f"<b>📋 Проверьте ваши ставки:</b>\n\n"
                f"<b>🌟 Основные ставки (5):</b>\n"
            )
            
            total_potential = 0.0
            
            for fight in sorted_fights:
                winner = selected_winners.get(fight.id)
                if winner:
                    winner_name = fight.fighter1_name if winner == 1 else fight.fighter2_name
                    odds = float(fight.odds1) if winner == 1 else float(fight.odds2)
                    total_potential += odds
                    text += f"• Бой {fight.fight_order}: <b>{winner_name}</b> (коэф: {odds:.2f})\n"
            
            # Страховка
            if insurance_id and insurance_winner:
                ins_fight = fights_dict.get(insurance_id)
                if ins_fight:
                    winner_name = ins_fight.fighter1_name if insurance_winner == 1 else ins_fight.fighter2_name
                    odds = float(ins_fight.odds1) if insurance_winner == 1 else float(ins_fight.odds2)
                    text += f"\n<b>🛡️ Страховочная ставка:</b>\n"
                    text += f"• Бой {ins_fight.fight_order}: <b>{winner_name}</b> (коэф: {odds:.2f})\n"
            
            text += f"\n<b>💰 Потенциальный выигрыш:</b> {total_potential:.2f} очков\n"
            text += "<i>Если все 5 основных ставок сыграют</i>\n\n"
            text += "<b>Сохранить эти ставки?</b>"
            
            buttons = [
                [InlineKeyboardButton(text="✅ Сохранить ставки", callback_data=f"confirm_save:{event_id}")],
                [InlineKeyboardButton(text="⬅️ Изменить страховку", callback_data=f"select_insurance:{event_id}")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="menu_current")]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в show_final_confirmation: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )


@router.callback_query(lambda c: c.data.startswith("save_bets:"))
async def process_save_bets(callback: CallbackQuery):
    """Показ финального подтверждения (роутинг)"""
    await show_final_confirmation(callback)


@router.callback_query(lambda c: c.data.startswith("confirm_save:"))
async def process_confirm_save(callback: CallbackQuery):
    """Финальное сохранение всех ставок в базу данных"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        betting_data = temp_event_data.get('betting_data', {}).get(user_id)
        
        if not betting_data:
            await callback.answer("❌ Данные не найдены", show_alert=True)
            return
        
        await callback.answer("💾 Сохраняю ставки...")
        
        from db_utils import get_session, save_user_bets
        from database import Bet
        from sqlalchemy import select
        
        async with get_session() as session:
            # Удаляем старые ставки пользователя на этот турнир
            await session.execute(
                select(Bet).where(
                    Bet.user_id == user_id,
                    Bet.event_id == event_id
                )
            )
            old_bets = (await session.execute(
                select(Bet).where(
                    Bet.user_id == user_id,
                    Bet.event_id == event_id
                )
            )).scalars().all()
            
            for bet in old_bets:
                await session.delete(bet)
            
            # Создаём новые ставки
            fights_dict = {f.id: f for f in betting_data['fights']}
            selected_fights = betting_data['selected_main_fights']
            selected_winners = betting_data['selected_winners']
            
            # Основные ставки
            for fight_id in selected_fights:
                fight = fights_dict.get(fight_id)
                winner = selected_winners.get(fight_id)
                
                if fight and winner:
                    odds = Decimal(str(fight.odds1)) if winner == 1 else Decimal(str(fight.odds2))
                    
                    bet = Bet(
                        user_id=user_id,
                        event_id=event_id,
                        fight_id=fight_id,
                        bet_type='main',
                        chosen_fighter=winner,
                        odds_at_bet=odds,
                        status='pending'
                    )
                    session.add(bet)
            
            # Страховочная ставка
            insurance_id = betting_data.get('insurance_fight_id')
            insurance_winner = betting_data.get('insurance_winner')
            
            if insurance_id and insurance_winner:
                ins_fight = fights_dict.get(insurance_id)
                if ins_fight:
                    odds = Decimal(str(ins_fight.odds1)) if insurance_winner == 1 else Decimal(str(ins_fight.odds2))
                    
                    bet = Bet(
                        user_id=user_id,
                        event_id=event_id,
                        fight_id=insurance_id,
                        bet_type='insurance',
                        chosen_fighter=insurance_winner,
                        odds_at_bet=odds,
                        status='pending'
                    )
                    session.add(bet)
            
            await session.commit()
        
        # Очищаем временные данные
        if user_id in temp_event_data.get('betting_data', {}):
            del temp_event_data['betting_data'][user_id]
        
        await callback.message.edit_text(
            "✅ <b>Ставки успешно сохранены!</b>\n\n"
            "Вы можете изменить их в любой момент до начала турнира.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_back")],
                [InlineKeyboardButton(text="🥊 К турниру", callback_data="menu_current")]
            ]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в confirm_save: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка сохранения: {str(e)[:100]}",
            reply_markup=get_back_button()
        )
