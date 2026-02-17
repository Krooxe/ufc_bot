"""
Обработчики архива турниров и рейтинга
Архив завершённых турниров, детальный просмотр, общий рейтинг
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from utils.keyboards import get_back_button

logger = logging.getLogger(__name__)

# Создаём роутер для архива
router = Router()


@router.callback_query(lambda c: c.data == "menu_archive")
async def process_archive(callback: CallbackQuery):
    """Показывает архив турниров"""
    try:
        await callback.answer()
        
        from db_utils import get_session, get_finished_events
        from database import Event
        from sqlalchemy import select
        
        async with get_session() as session:
            # Получаем завершенные турниры
            result = await session.execute(
                select(Event)
                .where(Event.status == 'finished')
                .order_by(Event.date_utc.desc())
            )
            events = result.scalars().all()
            
            if not events:
                text = "🏆 <b>Архив турниров</b>\n\nПока завершенных турниров нет."
                keyboard = get_back_button()
            else:
                text = "🏆 <b>Архив турниров</b>\n\nВыберите турнир для просмотра:\n\n"
                
                # Формируем список турниров
                buttons = []
                for event in events[:10]:  # Показываем последние 10
                    date_str = event.date_utc.strftime('%d.%m.%Y')
                    btn_text = f"{event.short_title} ({date_str})"
                    callback_data = f"view_archive:{event.id}"
                    buttons.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])
                
                buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back")])
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в process_archive: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )


@router.callback_query(lambda c: c.data.startswith("view_archive:"))
async def process_view_archive(callback: CallbackQuery):
    """Показывает детали турнира из архива"""
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer("📊 Загружаю результаты турнира...")
        
        from db_utils import get_session, get_event_by_id, get_fights_for_event, get_user_bets_for_event
        from database import User, Bet
        from sqlalchemy import select
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            fights = await get_fights_for_event(session, event_id)
            
            if not event or not fights:
                await callback.message.edit_text(
                    "❌ Турнир не найден",
                    reply_markup=get_back_button()
                )
                return
            
            # Получаем всех пользователей
            users_result = await session.execute(select(User))
            all_users = users_result.scalars().all()
            
            # Получаем все ставки на этот турнир
            all_bets_result = await session.execute(
                select(Bet).where(Bet.event_id == event_id)
            )
            all_bets = all_bets_result.scalars().all()
            
            # Группируем ставки по пользователям
            bets_by_user = {}
            for bet in all_bets:
                if bet.user_id not in bets_by_user:
                    bets_by_user[bet.user_id] = []
                bets_by_user[bet.user_id].append(bet)
            
            # Словарь боев для быстрого поиска
            fights_dict = {f.id: f for f in fights}
            
            # Формируем текст
            text = f"🏆 <b>Архив: {event.title}</b>\n"
            text += f"📅 {event.date_utc.strftime('%d.%m.%Y')}\n"
            text += f"📊 Статус: <b>{event.status}</b>\n\n"
            
            # Результаты боев
            text += "<b>Результаты боев:</b>\n"
            for fight in fights:
                # Определяем иконку результата
                if fight.winner == '1':
                    result_icon = "👊"
                    result_text = f"{fight.fighter1_name} победил"
                elif fight.winner == '2':
                    result_icon = "🥊"
                    result_text = f"{fight.fighter2_name} победил"
                elif fight.winner == 'draw':
                    result_icon = "🤝"
                    result_text = "Ничья"
                elif fight.winner in ['nc', 'cancelled']:
                    result_icon = "❌"
                    result_text = "Не состоялся"
                else:
                    result_icon = "❓"
                    result_text = "Нет результата"
                
                # Выводим информацию о бое
                text += f"<b>{fight.fight_order}. {fight.fighter1_name} vs {fight.fighter2_name}</b>\n"
                text += f"   {result_icon} <i>{result_text}</i>\n"
                
                # Коэффициенты если есть
                if fight.odds1 is not None and fight.odds2 is not None:
                    text += f"   Коэффициенты: {fight.odds1:.2f} / {fight.odds2:.2f}\n"
                
                text += "\n"
            
            # Результаты игроков с НАКОПЛЕННЫМИ ОЧКАМИ
            text += "<b>Результаты игроков:</b>\n\n"
            
            # Собираем данные по каждому игроку
            players_data = []
            
            for user in all_users:
                username = user.username or user.full_name or f"Игрок {user.user_id}"
                
                if user.user_id in bets_by_user:
                    user_bets = bets_by_user[user.user_id]
                    
                    # Разделяем ставки
                    main_bets = [b for b in user_bets if b.bet_type == 'main']
                    insurance_bet = next((b for b in user_bets if b.bet_type == 'insurance'), None)
                    
                    # Сортируем основные ставки по fight_order
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
                    
                    # Считаем очки за этот турнир
                    tournament_points = 0.0
                    bet_details = []
                    
                    # Обрабатываем основные ставки
                    for item in sorted_main_bets:
                        bet = item['bet']
                        fight = item['fight']
                        fighter_name = fight.fighter1_name if bet.chosen_fighter == 1 else fight.fighter2_name
                        
                        # Определяем результат ставки
                        if bet.status == 'win' and bet.points_earned:
                            result_icon = "✅"
                            points = float(bet.points_earned)
                            points_text = f"+{points:.2f}"
                            tournament_points += points
                        elif bet.status == 'lose':
                            result_icon = "❌"
                            points_text = "0.00"
                        elif bet.status == 'cancelled':
                            result_icon = "➖"
                            points_text = "0.00"
                        else:
                            result_icon = "❓"
                            points_text = "?"
                        
                        bet_details.append(f"{result_icon} Бой {fight.fight_order}: {fighter_name} ({points_text})")
                    
                    # Обрабатываем страховочную ставку
                    if insurance_bet:
                        fight = fights_dict.get(insurance_bet.fight_id)
                        if fight:
                            fighter_name = fight.fighter1_name if insurance_bet.chosen_fighter == 1 else fight.fighter2_name
                            
                            if insurance_bet.status == 'win' and insurance_bet.points_earned:
                                points = float(insurance_bet.points_earned)
                                bet_details.append(f"🛡️ Страховка (бой {fight.fight_order}): {fighter_name} (+{points:.2f})")
                                tournament_points += points
                            elif insurance_bet.status == 'win':
                                bet_details.append(f"🛡️ Страховка (бой {fight.fight_order}): {fighter_name} (+0.00)")
                            else:
                                bet_details.append(f"🛡️ Страховка (бой {fight.fight_order}): {fighter_name} (не понадобилась)")
                    
                    # Считаем НАКОПЛЕННЫЕ очки за год (до этого турнира включительно)
                    from sqlalchemy import select as sql_select, func
                    from database import Bet as BetModel, Event as EventModel
                    
                    year_points_result = await session.execute(
                        sql_select(func.sum(BetModel.points_earned))
                        .join(EventModel, BetModel.event_id == EventModel.id)
                        .where(
                            BetModel.user_id == user.user_id,
                            EventModel.year == event.year,
                            EventModel.date_utc <= event.date_utc  # Все турниры этого года до текущего включительно
                        )
                    )
                    year_points = year_points_result.scalar() or 0.0
                    accumulated_points = float(year_points)
                    
                    players_data.append({
                        'user': user,
                        'username': username,
                        'tournament_points': tournament_points,
                        'accumulated_points': accumulated_points,
                        'bet_details': bet_details,
                        'has_bets': True
                    })
                    
                else:
                    # Игрок без ставок
                    players_data.append({
                        'user': user,
                        'username': username,
                        'tournament_points': 0.0,
                        'accumulated_points': 0.0,
                        'bet_details': ["Ставок не делал"],
                        'has_bets': False
                    })
            
            # Сортируем игроков по очкам за турнир (по убыванию)
            players_data.sort(key=lambda x: x['tournament_points'], reverse=True)
            
            # Выводим отсортированных игроков
            for i, player in enumerate(players_data, 1):
                medal = ""
                if i == 1 and player['tournament_points'] > 0:
                    medal = "🥇"
                elif i == 2 and player['tournament_points'] > 0:
                    medal = "🥈"
                elif i == 3 and player['tournament_points'] > 0:
                    medal = "🥉"
                
                text += f"{medal} <b>{i}. {player['username']}</b>\n"
                text += f"   <i>Турнир:</i> {player['tournament_points']:.2f} очков\n"
                text += f"   <i>Накоплено в {event.year} году:</i> {player['accumulated_points']:.2f} очков\n"
                
                # Выводим детали ставок
                for detail in player['bet_details']:
                    text += f"   {detail}\n"
                
                text += "\n"
            
            # Кнопки
            buttons = [
                [InlineKeyboardButton(text="⬅️ Назад в архив", callback_data="menu_archive")]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в view_archive: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )


@router.callback_query(lambda c: c.data == "menu_rating")
async def process_rating(callback: CallbackQuery):
    """Показывает общий рейтинг (накопленные очки за текущий год)"""
    try:
        await callback.answer()
        
        from db_utils import get_session
        from database import User, Bet, Event
        from sqlalchemy import select, func
        
        async with get_session() as session:
            current_year = datetime.now().year
            
            # Получаем пользователей с их общим балансом за текущий год
            query = (
                select(
                    User.user_id,
                    User.username,
                    User.full_name,
                    func.coalesce(func.sum(Bet.points_earned), 0).label('total_points')
                )
                .join(Bet, Bet.user_id == User.user_id, isouter=True)
                .join(Event, Bet.event_id == Event.id, isouter=True)
                .where(
                    (Event.year == current_year) | (Event.id.is_(None))
                )
                .group_by(User.user_id, User.username, User.full_name)
                .order_by(func.coalesce(func.sum(Bet.points_earned), 0).desc())
            )
            
            result = await session.execute(query)
            users_with_points = result.all()
            
            if not users_with_points:
                text = "📈 <b>Общий рейтинг</b>\n\nПока нет данных за текущий год."
            else:
                text = f"📈 <b>Общие итоги ({current_year} год)</b>\n\n"
                
                for i, (user_id, username, full_name, total_points) in enumerate(users_with_points, 1):
                    # Используем лучшее доступное имя
                    display_name = username or full_name or f"Игрок {user_id}"
                    
                    # Форматируем очки
                    points_value = float(total_points) if total_points else 0.0
                    
                    text += f"<b>{i}. {display_name}: {points_value:.2f}</b>\n"
        
        await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в process_rating: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )
