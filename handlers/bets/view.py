"""
Просмотр детальной информации о ставках пользователя
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.keyboards import get_back_button

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data.startswith("my_bets_detail:"))
async def process_my_bets_detail(callback: CallbackQuery):
    """Детальные мои ставки"""
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer("📊 Загружаю детальные ставки...")
        
        from db_utils import get_session, get_user_bets_for_event, get_fights_for_event, get_event_by_id
        
        async with get_session() as session:
            bets = await get_user_bets_for_event(session, callback.from_user.id, event_id)
            fights = await get_fights_for_event(session, event_id)
            event = await get_event_by_id(session, event_id)
            
            if not event:
                text = "❌ Турнир не найден"
                keyboard = get_back_button()
                await callback.message.edit_text(text, reply_markup=keyboard)
                return
            
            fights_dict = {f.id: f for f in fights}
            
            if not bets:
                text = f"📊 <b>Ваши ставки на {event.title}</b>\n\nУ вас нет ставок на этот турнир."
            else:
                text = f"📊 <b>Ваши ставки на {event.title}</b>\n\n"
                
                # Разделяем ставки
                main_bets = [b for b in bets if b.bet_type == 'main']
                insurance_bets = [b for b in bets if b.bet_type == 'insurance']
                
                # СОРТИРУЕМ основные ставки по fight_order
                main_bets_sorted = []
                for bet in main_bets:
                    fight = fights_dict.get(bet.fight_id)
                    if fight:
                        main_bets_sorted.append({
                            'bet': bet,
                            'fight_order': fight.fight_order,
                            'fight': fight
                        })
                
                main_bets_sorted.sort(key=lambda x: x['fight_order'])
                
                if main_bets:
                    text += "<b>🌟 Основные ставки (5):</b>\n"
                    for item in main_bets_sorted:
                        bet = item['bet']
                        fight = item['fight']
                        
                        fighter_name = fight.fighter1_name if bet.chosen_fighter == 1 else fight.fighter2_name
                        status_icon = "⏳" if bet.status == 'pending' else "✅" if bet.status == 'win' else "❌"
                        text += f"• {status_icon} Бой {fight.fight_order}: <b>{fighter_name}</b> (коэф: <b>{bet.odds_at_bet:.2f}</b>) - {bet.status}\n"
                
                # Страховочная ставка
                if insurance_bets:
                    text += "\n<b>🛡️ Страховочная ставка:</b>\n"
                    for bet in insurance_bets:
                        fight = fights_dict.get(bet.fight_id)
                        if fight:
                            fighter_name = fight.fighter1_name if bet.chosen_fighter == 1 else fight.fighter2_name
                            status_icon = "⏳" if bet.status == 'pending' else "✅" if bet.status == 'win' else "❌"
                            text += f"• {status_icon} Бой {fight.fight_order}: <b>{fighter_name}</b> (коэф: <b>{bet.odds_at_bet:.2f}</b>) - {bet.status}\n"
                
                # Общая информация
                total_potential = sum(float(b.odds_at_bet) for b in main_bets if b.odds_at_bet)
                text += f"\n<b>💰 Потенциальный выигрыш:</b> {total_potential:.2f} очков\n"
                text += f"<i>Если все 5 основных ставок сыграют</i>"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Изменить ставки", callback_data=f"make_bets:{event_id}")],
                [InlineKeyboardButton(text="⬅️ Назад к турниру", callback_data="menu_current")]
            ]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в my_bets_detail: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )
