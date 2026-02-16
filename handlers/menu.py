"""
Обработчики главного меню
Баланс, текущий турнир, возврат назад
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

from utils.keyboards import get_back_button, get_main_menu
from utils.states import temp_event_data

logger = logging.getLogger(__name__)

# Создаём роутер для меню
router = Router()


@router.callback_query(lambda c: c.data == "menu_balance")
async def process_balance(callback: CallbackQuery):
    """Показывает баланс пользователя"""
    try:
        await callback.answer()
        text = "💰 <b>Твой баланс:</b> 0.00 очков\n\nЗдесь будут твои очки и статистика."
        await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Ошибка в process_balance: {e}")


@router.callback_query(lambda c: c.data == "menu_current")
async def process_current(callback: CallbackQuery):
    """Показывает текущий турнир с детальной информацией о ставках"""
    try:
        await callback.answer()
        
        from db_utils import get_open_event_with_fights, get_session, get_or_create_user
        from database import Bet, Fight, User
        from sqlalchemy import select
        
        async with get_session() as session:
            # 1. Получаем открытый турнир
            event_data = await get_open_event_with_fights(session)
            
            if not event_data:
                text = "🥊 <b>Текущий турнир</b>\n\n🏆 Активных турниров пока нет."
                keyboard = get_back_button()
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
                return
            
            event = event_data['event']
            fights = event_data['fights']
            
            # 2. Создаём/получаем пользователя
            user = await get_or_create_user(
                session,
                callback.from_user.id,
                callback.from_user.username,
                callback.from_user.full_name
            )

            # ДОБАВЛЯЕМ СРАЗУ ПОСЛЕ СОЗДАНИЯ ПОЛЬЗОВАТЕЛЯ:
            #await session.commit()
            
            # 3. Получаем ВСЕХ пользователей (наших игроков)
            users_result = await session.execute(
                select(User).order_by(User.created_at.asc())
            )
            all_users = users_result.scalars().all()
            
            # 4. Получаем все ставки на этот турнир
            all_bets_result = await session.execute(
                select(Bet).where(Bet.event_id == event.id)
            )
            all_bets = all_bets_result.scalars().all()
            
            # Группируем ставки по пользователям
            bets_by_user = {}
            for bet in all_bets:
                if bet.user_id not in bets_by_user:
                    bets_by_user[bet.user_id] = []
                bets_by_user[bet.user_id].append(bet)
            
            # Создаем словарь для быстрого поиска боев
            fights_dict = {fight.id: fight for fight in fights}
            
            # 5. Формируем текст
            
            # Информация о турнире
            tournament_info = (
                f"🥊 <b>Текущий турнир</b>\n\n"
                f"🏆 <b>{event.title}</b>\n"
                f"📅 <b>Дата:</b> {event.date_utc.strftime('%d.%m.%Y %H:%M')} UTC\n"
                f"🥊 <b>Боев:</b> {len(fights)}\n"
                f"👥 <b>Участников:</b> {len(all_users)}\n\n"
            )
            
                        # Ставки текущего пользователя
            user_bets_text = ""
            if callback.from_user.id in bets_by_user:
                user_bets_text = "🎯 <b>Ваши ставки:</b>\n"
                
                # Получаем и сортируем ставки пользователя
                user_bets_list = bets_by_user[callback.from_user.id]
                main_bets = [b for b in user_bets_list if b.bet_type == 'main']
                
                # Создаем список для сортировки
                sorted_main_bets = []
                for bet in main_bets:
                    fight = fights_dict.get(bet.fight_id)
                    if fight:
                        sorted_main_bets.append({
                            'bet': bet,
                            'fight_order': fight.fight_order,
                            'fight': fight
                        })
                
                # СОРТИРУЕМ по fight_order
                sorted_main_bets.sort(key=lambda x: x['fight_order'])
                
                # Выводим отсортированные ставки
                for item in sorted_main_bets:
                    bet = item['bet']
                    fight = item['fight']
                    fighter_name = fight.fighter1_name if bet.chosen_fighter == 1 else fight.fighter2_name
                    odds = bet.odds_at_bet
                    user_bets_text += f"• Бой {fight.fight_order}: <b>{fighter_name}</b> ({odds:.2f})\n"
                
                # Страховочная ставка
                insurance_bets = [b for b in user_bets_list if b.bet_type == 'insurance']
                if insurance_bets:
                    bet = insurance_bets[0]
                    fight = fights_dict.get(bet.fight_id)
                    if fight:
                        fighter_name = fight.fighter1_name if bet.chosen_fighter == 1 else fight.fighter2_name
                        odds = bet.odds_at_bet
                        user_bets_text += f"• 🛡️ Страховка (бой {fight.fight_order}): <b>{fighter_name}</b> ({odds:.2f})\n"
            else:
                user_bets_text = "🎯 <b>Ваши ставки:</b> пока нет\n"
            
                        # Ставки других игроков (ПОЛНЫЙ СПИСОК)
            other_players_text = "\n<b>👥 Ставки других игроков:</b>\n"
            players_without_bets = 0
            players_with_bets = 0
            
            for other_user in all_users:
                if other_user.user_id == callback.from_user.id:
                    continue  # Пропускаем текущего пользователя
                
                username = other_user.username or other_user.full_name or f"Игрок {other_user.user_id}"
                
                if other_user.user_id in bets_by_user:
                    players_with_bets += 1
                    other_players_text += f"\n<b>{username}:</b>\n"
                    
                    # Получаем все ставки этого игрока
                    user_bets_list = bets_by_user[other_user.user_id]
                    
                    # Разделяем основные и страховочные
                    main_bets = [b for b in user_bets_list if b.bet_type == 'main']
                    insurance_bets = [b for b in user_bets_list if b.bet_type == 'insurance']
                    
                    # СОРТИРУЕМ основные ставки по fight_order
                    sorted_main_bets = []
                    for bet in main_bets:
                        fight = fights_dict.get(bet.fight_id)
                        if fight:
                            sorted_main_bets.append({
                                'bet': bet,
                                'fight_order': fight.fight_order,
                                'fight': fight
                            })
                    
                    sorted_main_bets.sort(key=lambda x: x['fight_order'])
                    
                    # Показываем ВСЕ основные ставки (как у себя)
                    for item in sorted_main_bets:
                        bet = item['bet']
                        fight = item['fight']
                        fighter_name = fight.fighter1_name if bet.chosen_fighter == 1 else fight.fighter2_name
                        # Для других игроков НЕ показываем коэффициенты (чтобы не спойлерить)
                        other_players_text += f"• Бой {fight.fight_order}: {fighter_name}\n"
                    
                    # Страховочная ставка (если есть)
                    if insurance_bets:
                        bet = insurance_bets[0]
                        fight = fights_dict.get(bet.fight_id)
                        if fight:
                            fighter_name = fight.fighter1_name if bet.chosen_fighter == 1 else fight.fighter2_name
                            other_players_text += f"• 🛡️ Страховка (бой {fight.fight_order}): {fighter_name}\n"
                else:
                    players_without_bets += 1
                    other_players_text += f"\n<b>{username}:</b> ставку ещё не делал\n"
            
            # Статистика
            stats_text = f"\n<b>📊 Статистика:</b>\n"
            stats_text += f"• Сделали ставки: {players_with_bets} игроков\n"
            stats_text += f"• Ждут: {players_without_bets} игроков\n"
            if event.status == 'open_for_bets':
                stats_text += f"• Статус: <b>принимаются ставки</b> ✅\n"
            else:
                stats_text += f"• Статус: <b>{event.status}</b>\n"
            
            # Собираем весь текст
            text = tournament_info + user_bets_text + other_players_text + stats_text
            
            # Кнопки
            buttons = []
            if callback.from_user.id not in bets_by_user:
                buttons.append([InlineKeyboardButton(text="🎯 Сделать ставки", callback_data=f"make_bets:{event.id}")])
            else:
                buttons.append([InlineKeyboardButton(text="✏️ Изменить ставки", callback_data=f"make_bets:{event.id}")])
                buttons.append([InlineKeyboardButton(text="📊 Детали моих ставок", callback_data=f"my_bets_detail:{event.id}")])
            
            buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в process_current: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )


async def update_fight_selection_message(message: Message, user_id: int, event_id: int):
    """Обновляет сообщение с выбором боев"""
    try:
        from db_utils import get_session, get_fights_for_event, get_event_by_id
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            fights = await get_fights_for_event(session, event_id)
            
            if not event or not fights:
                return
            
            betting_data = temp_event_data['betting_data'][user_id]
            selected_count = len(betting_data['selected_main_fights'])
            
            # Формируем текст с подсветкой выбранных боев
            fights_text = ""
            for i, fight in enumerate(fights, 1):
                odds1 = f"{fight.odds1:.2f}" if fight.odds1 else "?"
                odds2 = f"{fight.odds2:.2f}" if fight.odds2 else "?"
                
                # Подсвечиваем выбранные бои
                if fight.id in betting_data['selected_main_fights']:
                    fights_text += f"✅ <b>{i}. {fight.fighter1_name} ({odds1}) vs {fight.fighter2_name} ({odds2})</b>\n"
                else:
                    fights_text += f"{i}. {fight.fighter1_name} ({odds1}) vs {fight.fighter2_name} ({odds2})\n"
            
            text = (
                f"🎯 <b>Сделать ставки: Шаг 1 из 4</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
                f"<b>Выберите 5 основных боев:</b>\n"
                f"(нажмите на номера боев, которые хотите выбрать)\n\n"
                f"{fights_text}\n"
                f"<b>Выбрано: {selected_count}/5</b>\n"
                f"<i>Выбирайте бои, на исход которых хотите поставить.</i>"
            )
            
            # Создаём инлайн-кнопки
            buttons = []
            row = []
            for i, fight in enumerate(fights, 1):
                btn_text = f"{i}"
                callback_data = f"select_fight:{event_id}:{fight.id}"
                
                # Подсвечиваем выбранные кнопки
                if fight.id in betting_data['selected_main_fights']:
                    btn_text = f"✅ {i}"
                
                row.append(InlineKeyboardButton(text=btn_text, callback_data=callback_data))
                
                if len(row) == 3:
                    buttons.append(row)
                    row = []
            
            if row:
                buttons.append(row)
            
            # Кнопки управления
            control_buttons = []
            
            if selected_count == 5:
                control_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"confirm_main:{event_id}"))
            
            control_buttons.append(InlineKeyboardButton(text="🔄 Сбросить", callback_data=f"reset_main:{event_id}"))
            buttons.append(control_buttons)
            buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_current")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в update_fight_selection_message: {e}")


@router.callback_query(lambda c: c.data == "menu_back")
async def process_back(callback: CallbackQuery):
    """Возврат в главное меню"""
    try:
        await callback.answer()
        await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu())
    except Exception as e:
        logger.warning(f"Ошибка в process_back: {e}")
