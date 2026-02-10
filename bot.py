import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
import config
from database import create_tables
from db_utils import get_session, get_fights_for_event, update_fight_odds_batch, open_event_for_bets, get_draft_events, create_event_from_api, get_event_by_id, get_events_for_odds_edit

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация FSM хранилища и диспетчера
storage = MemoryStorage()
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=storage)

# ==================== СОСТОЯНИЯ (FSM) ====================

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_odds = State()  # Ожидание ввода коэффициентов
    waiting_for_results = State()  # Ожидание ввода результатов
    waiting_for_announcement = State()  # Ожидание текста объявления
    
# Глобальная переменная для хранения временных данных
temp_event_data = {}

# ==================== INLINE-КЛАВИАТУРЫ ====================

def get_main_menu() -> InlineKeyboardMarkup:
    """Создает главное меню с inline-кнопками"""
    buttons = [
        [InlineKeyboardButton(text="📊 Мой баланс", callback_data="menu_balance")],
        [InlineKeyboardButton(text="🥊 Текущий турнир", callback_data="menu_current")],
        [InlineKeyboardButton(text="📈 Общий рейтинг", callback_data="menu_rating")],
        [InlineKeyboardButton(text="🏆 Архив", callback_data="menu_archive")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_button() -> InlineKeyboardMarkup:
    """Кнопка 'Назад' в главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_back")]
    ])

# ==================== АДМИН-ПАНЕЛЬ ====================

def get_admin_menu() -> InlineKeyboardMarkup:
    """Меню админ-панели"""
    buttons = [
        [InlineKeyboardButton(text="➕ Новый PPV", callback_data="admin_new_ppv")],
        [InlineKeyboardButton(text="📥 Ввести кэфы", callback_data="admin_add_odds")],
        [InlineKeyboardButton(text="🏁 Закрыть турнир", callback_data="admin_close_event")],  # НОВАЯ КНОПКА
        [InlineKeyboardButton(text="📢 Объявление", callback_data="admin_announce")],
        [InlineKeyboardButton(text="ℹ️ Статус", callback_data="admin_status")],
        [InlineKeyboardButton(text="✖️ Выход", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== ХЕНДЛЕРЫ КОМАНД ====================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Обработка команды /start"""
    user = message.from_user
    
    welcome_text = (
        f"👊 Привет, {user.first_name}!\n\n"
        f"Я бот для ставок на UFC. Твой ID: {user.id}\n"
        "Следи за турнирами, делай ставки и соревнуйся с друзьями!\n\n"
        "⬇️ Используй меню ниже:"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_menu())
    
    # СОЗДАЁМ/ПОЛУЧАЕМ ПОЛЬЗОВАТЕЛЯ В БАЗЕ
    try:
        from db_utils import get_session, get_or_create_user
        
        async with get_session() as session:
            db_user = await get_or_create_user(
                session,
                user.id,
                user.username,
                user.full_name
            )
            logger.info(f"Пользователь в БД: {db_user.user_id} - {db_user.username}")
    except Exception as e:
        logger.error(f"Ошибка создания пользователя: {e}")

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда /admin - только для админа"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ У вас нет прав доступа к админ-панели.")
        return
    
    text = (
        f"⚙️ <b>Админ-панель</b>\n\n"
        f"Привет, админ {message.from_user.first_name}!\n"
        f"ID: {message.from_user.id}\n\n"
        f"Выберите действие:"
    )
    
    await message.answer(text, reply_markup=get_admin_menu(), parse_mode="HTML")
    logger.info(f"Админ вошел: {message.from_user.id}")

# ==================== ОБРАБОТЧИКИ INLINE-КНОПОК ====================

@dp.callback_query(lambda c: c.data == "menu_balance")
async def process_balance(callback: CallbackQuery):
    """Показывает баланс пользователя"""
    try:
        await callback.answer()
        text = "💰 <b>Твой баланс:</b> 0.00 очков\n\nЗдесь будут твои очки и статистика."
        await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Ошибка в process_balance: {e}")

@dp.callback_query(lambda c: c.data == "menu_current")
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

@dp.callback_query(lambda c: c.data.startswith("my_bets_detail:"))
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

@dp.callback_query(lambda c: c.data == "menu_archive")
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

@dp.callback_query(lambda c: c.data.startswith("view_archive:"))
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
            
            # Статистика турнира
            text += "<b>📊 Статистика турнира:</b>\n"
            players_with_bets = sum(1 for p in players_data if p['has_bets'])
            max_points = max((p['tournament_points'] for p in players_data), default=0)
            avg_points = sum(p['tournament_points'] for p in players_data) / len(players_data) if players_data else 0
            
            text += f"• Участников: {len(players_data)}\n"
            text += f"• Сделали ставки: {players_with_bets}\n"
            text += f"• Максимум очков: {max_points:.2f}\n"
            text += f"• Среднее: {avg_points:.2f} очков\n"
            
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
        
@dp.callback_query(lambda c: c.data == "menu_rating")
async def process_rating(callback: CallbackQuery):
    """Показывает общий рейтинг (накопленные очки за текущий год)"""
    try:
        await callback.answer()
        
        from db_utils import get_session
        from database import User, Bet, Event
        from sqlalchemy import select, func
        from datetime import datetime
        
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

@dp.callback_query(lambda c: c.data == "menu_back")
async def process_back(callback: CallbackQuery):
    """Возврат в главное меню"""
    try:
        await callback.answer()
        await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu())
    except Exception as e:
        logger.warning(f"Ошибка в process_back: {e}")

# ==================== ОБРАБОТЧИКИ АДМИНСКИХ КНОПОК ====================
@dp.callback_query(lambda c: c.data == "admin_close_event")
async def process_admin_close_event(callback: CallbackQuery):
    """Закрытие турнира - выбор из списка"""
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        await callback.answer("🏁 Выбор турнира для закрытия")
        
        from db_utils import get_session, get_unfinished_events
        from database import Event, Fight
        from sqlalchemy import select
        
        async with get_session() as session:
            # Получаем незавершенные турниры
            unfinished_events = await get_unfinished_events(session)
            
            if not unfinished_events:
                text = (
                    "🏁 <b>Закрытие турнира</b>\n\n"
                    "Нет турниров для закрытия.\n"
                    "Все турниры уже завершены или пока нет активных."
                )
                keyboard = get_admin_menu()
            else:
                text = "🏁 <b>Выберите турнир для закрытия:</b>\n\n"
                
                buttons = []
                for event in unfinished_events:
                    # Получаем статистику по боям
                    fights_result = await session.execute(
                        select(Fight).where(Fight.event_id == event.id)
                    )
                    fights = fights_result.scalars().all()
                    
                    # Считаем бои с результатами и без
                    total_fights = len(fights)
                    finished_fights = sum(1 for f in fights if f.winner is not None)
                    
                    btn_text = (
                        f"{event.short_title} ({event.date_utc.strftime('%d.%m')}) - "
                        f"{finished_fights}/{total_fights} боев"
                    )
                    
                    buttons.append([
                        InlineKeyboardButton(
                            text=btn_text,
                            callback_data=f"admin_confirm_close:{event.id}"
                        )
                    ])
                
                buttons.append([
                    InlineKeyboardButton(text="↩️ Назад", callback_data="admin_status")
                ])
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_close_event: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("admin_") 
                   and not c.data.startswith("admin_input_odds:") 
                   and not c.data.startswith("admin_confirm_close:")
                   and not c.data.startswith("admin_execute_close:")
                   and not c.data.startswith("admin_update_single:")
                   and not c.data.startswith("admin_calculate_points:")
                   and c.data != "admin_create_draft"
                   and c.data != "admin_close_event"
                   and c.data != "admin_update_all")
async def process_admin_commands(callback: CallbackQuery):
    """Обработка всех админских команд"""
    logger.info(f"Админ-кнопка: {callback.data} от user_id={callback.from_user.id}")
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        data = callback.data
        
        if data == "admin_new_ppv":
            await callback.answer("🔄 Получаю данные с ufcstats.com...")
            from ufc_api import get_upcoming_event, get_event_fights
            from datetime import datetime, timezone
            
            # Получаем второй турнир с ufcstats.com
            next_ppv = await get_upcoming_event()
            if not next_ppv:
                await callback.message.edit_text("❌ Не удалось получить турнир с ufcstats.com.", reply_markup=get_admin_menu())
                return
            
            # Парсим дату локально
            date_iso = next_ppv.get('date', '').replace('Z', '+00:00')
            event_date = datetime.fromisoformat(date_iso)
            date_str = event_date.strftime("%d.%m.%Y %H:%M UTC")
            
            fights = get_event_fights(next_ppv)
            
            if not fights:
                await callback.message.edit_text("❌ Нет данных о боях.", reply_markup=get_admin_menu())
                return
            
            # Сохраняем данные
            temp_event_data[callback.from_user.id] = {
                'event': next_ppv,
                'fights': fights
            }
            logger.info(f"Сохранены данные для user_id={callback.from_user.id}")
            
            fights_text = "\n".join([
                f"{i}. {fight.get('fighter1', {}).get('name', 'N/A')} vs {fight.get('fighter2', {}).get('name', 'N/A')}"
                for i, fight in enumerate(fights, 1)
            ])
            
            text = (
                f"✅ <b>Найден PPV турнир!</b>\n\n"
                f"🏆 <b>{next_ppv.get('name', 'N/A')}</b>\n"
                f"📅 <b>Дата:</b> {date_str}\n"
                f"🥊 <b>Боев:</b> {len(fights)}\n\n"
                f"{fights_text}"
            )
            
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Создать черновик", callback_data="admin_create_draft")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_status")]
                ]),
                parse_mode="HTML"
            )
            
        elif data == "admin_add_odds":
            await callback.answer("📥 Ввод/редактирование коэффициентов")
            
            from db_utils import get_events_for_odds_edit, get_session, get_fights_for_event
            from database import Event
            
            async with get_session() as session:
                events = await get_events_for_odds_edit(session)
                
                if not events:
                    text = "📊 <b>Коэффициенты</b>\n\nНет турниров для редактирования коэффициентов."
                    keyboard = get_admin_menu()
                
                elif len(events) == 1:
                    # Если турнир один
                    event = events[0]
                    status_text = "черновик" if event.status == 'draft' else "открыт для ставок"
                    
                    fights = await get_fights_for_event(session, event.id)
                    
                    # Формируем список боев с коэффициентами
                    fights_list = ""
                    has_odds = False
                    for i, fight in enumerate(fights[:10], 1):
                        if fight.odds1 and fight.odds2:
                            has_odds = True
                            fights_list += f"{i}. {fight.fighter1_name} (<b>{fight.odds1}</b>) vs {fight.fighter2_name} (<b>{fight.odds2}</b>)\n"
                        else:
                            fights_list += f"{i}. {fight.fighter1_name} (?) vs {fight.fighter2_name} (?)\n"
                    
                    if len(fights) > 10:
                        fights_list += f"... и ещё {len(fights) - 10} боев\n"
                    
                    action_text = "ввести" if not has_odds else "изменить"
                    
                    text = (
                        f"📊 <b>Коэффициенты для {event.short_title}</b>\n\n"
                        f"Турнир: {event.title}\n"
                        f"Дата: {event.date_utc.strftime('%d.%m.%Y')}\n"
                        f"Статус: <b>{status_text}</b>\n"
                        f"Боев: {len(fights)}\n\n"
                        f"<b>Текущие коэффициенты:</b>\n"
                        f"{fights_list}\n"
                        f"Нажмите чтобы {action_text} коэффициенты:"
                    )
                    
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=f"📝 {action_text.capitalize()} коэффициенты", callback_data=f"admin_input_odds:{event.id}")],
                        [InlineKeyboardButton(text="↩️ Назад", callback_data="admin_status")]
                    ])
                
                else:
                    # Если несколько турниров
                    text = "📊 <b>Выберите турнир для редактирования коэффициентов:</b>\n\n"
                    buttons = []
                    for event in events:
                        status_icon = "📄" if event.status == 'draft' else "🎯"
                        btn_text = f"{status_icon} {event.short_title} ({event.date_utc.strftime('%d.%m')})"
                        callback_data = f"admin_input_odds:{event.id}"
                        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])
                    
                    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="admin_status")])
                    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
        elif data == "admin_results":
            await callback.answer("🏁 Ввод результатов")
            await callback.message.edit_text("🎯 <b>Ввод результатов</b>\n\nФункция в разработке.", reply_markup=get_admin_menu(), parse_mode="HTML")
            
        elif data == "admin_announce":
            await callback.answer("📢 Рассылка")
            await callback.message.edit_text("📢 <b>Рассылка</b>\n\nФункция в разработке.", reply_markup=get_admin_menu(), parse_mode="HTML")
            
        elif data == "admin_status":
            try:
                await callback.answer()
                
                from db_utils import get_session
                from database import User, Event
                from sqlalchemy import select
                
                async with get_session() as session:
                    result = await session.execute(select(User))
                    users = result.scalars().all()
                    user_count = len(users)
                    
                    result = await session.execute(select(Event))
                    events = result.scalars().all()
                    event_count = len(events)
                
                text = (
                    f"ℹ️ <b>Статус системы</b>\n\n"
                    f"• Бот работает ✅\n"
                    f"• Пользователей: {user_count}\n"
                    f"• Турниров в БД: {event_count}\n"
                    f"• Admin ID: {config.ADMIN_ID}"
                )
                await callback.message.edit_text(text, reply_markup=get_admin_menu(), parse_mode="HTML")
                
            except Exception as e:
                logger.error(f"Ошибка в admin_status: {e}")
                text = (
                    f"ℹ️ <b>Статус системы</b>\n\n"
                    f"• Бот работает ✅\n"
                    f"• Admin ID: {config.ADMIN_ID}\n"
                    f"• Ошибка БД: {str(e)[:50]}"
                )
                await callback.message.edit_text(text, reply_markup=get_admin_menu(), parse_mode="HTML")
            
    except Exception as e:
        logger.warning(f"Ошибка в админ-команде: {e}")

@dp.callback_query(lambda c: c.data.startswith("admin_confirm_close:"))
async def process_admin_confirm_close(callback: CallbackQuery):
    """Подтверждение закрытия турнира"""
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        event_id = int(callback.data.split(":")[1])
        
        from db_utils import get_session, get_event_by_id, get_fights_for_event, update_event_results_from_api
        from database import Event, Fight
        from sqlalchemy import select
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            if not event:
                await callback.answer("❌ Турнир не найден", show_alert=True)
                return
            
            # Получаем бои
            fights = await get_fights_for_event(session, event_id)
            
            # Считаем статистику
            total_fights = len(fights)
            finished_fights = sum(1 for f in fights if f.winner is not None)
            unfinished_fights = total_fights - finished_fights
            
            text = (
                f"🏁 <b>Подтверждение закрытия турнира</b>\n\n"
                f"<b>{event.title}</b>\n"
                f"Дата: {event.date_utc.strftime('%d.%m.%Y')}\n"
                f"Статус: {event.status}\n\n"
                f"<b>Статистика боев:</b>\n"
                f"• Всего боев: {total_fights}\n"
                f"• С результатами: {finished_fights}\n"
                f"• Без результатов: {unfinished_fights}\n\n"
            )
            
            if unfinished_fights > 0:
                text += (
                    f"⚠️ <b>Внимание!</b> {unfinished_fights} боев без результатов.\n"
                    f"При закрытии им будут присвоены результаты 'nc' (не состоялся).\n\n"
                )
            
            text += "Вы уверены, что хотите закрыть турнир?"
            
            buttons = [
                [
                    InlineKeyboardButton(
                        text="✅ Да, закрыть турнир", 
                        callback_data=f"admin_execute_close:{event_id}"
                    ),
                    InlineKeyboardButton(
                        text="🔄 Сначала обновить из API", 
                        callback_data=f"admin_update_single:{event_id}"
                    )
                ],
                [
                    InlineKeyboardButton(text="❌ Нет, отмена", callback_data="admin_close_event")
                ]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_confirm_close: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("admin_execute_close:"))
async def process_admin_execute_close(callback: CallbackQuery):
    """Выполнение закрытия турнира"""
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        event_id = int(callback.data.split(":")[1])
        await callback.answer("🔄 Закрываю турнир и считаю очки...")
        
        from db_utils import get_session, get_event_by_id, get_fights_for_event, mark_event_as_finished, calculate_user_points_for_event, update_event_results_from_api
        from database import Fight, User
        from sqlalchemy import select
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            if not event:
                await callback.answer("❌ Турнир не найден", show_alert=True)
                return
            
            # 1. Сначала обновляем результаты из API (если есть новые)
            await update_event_results_from_api(session, event)
            
            # 2. Получаем бои без результатов
            fights_result = await session.execute(
                select(Fight).where(
                    Fight.event_id == event_id,
                    Fight.winner.is_(None)
                )
            )
            unfinished_fights = fights_result.scalars().all()
            
            # 3. Проставляем 'nc' для боев без результатов
            for fight in unfinished_fights:
                fight.winner = 'nc'
            
            # 4. Помечаем турнир как завершенный (форсируем, даже если is_event_finished вернёт False)
            event.status = 'finished'
            await session.commit()
            
            # 5. Считаем очки для всех игроков
            users_result = await session.execute(select(User))
            all_users = users_result.scalars().all()
            
            total_points_calculated = 0
            for user in all_users:
                points = await calculate_user_points_for_event(session, user.user_id, event_id)
                if points > 0:
                    total_points_calculated += 1
            
            text = (
                f"✅ <b>Турнир закрыт!</b>\n\n"
                f"<b>{event.title}</b> теперь завершен.\n"
                f"Статус: <b>finished</b>\n"
                f"Обновлено боев: {len(unfinished_fights)}\n"
                f"Посчитаны очки для: {total_points_calculated} игроков\n\n"
                f"Результаты уже доступны в архиве."
            )
            
            # Кнопки
            buttons = [
                [InlineKeyboardButton(text="📊 Посмотреть архив", callback_data=f"view_archive:{event_id}")],
                [InlineKeyboardButton(text="📈 Общий рейтинг", callback_data="menu_rating")],
                [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_status")]
            ]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            logger.info(f"Турнир {event_id} закрыт, очки посчитаны")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_execute_close: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ <b>Ошибка:</b> {str(e)[:200]}",
            reply_markup=get_admin_menu(),
            parse_mode="HTML"
        )

@dp.callback_query(lambda c: c.data.startswith("admin_update_single:"))
async def process_admin_update_single(callback: CallbackQuery):
    """Обновление одного турнира из API"""
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        event_id = int(callback.data.split(":")[1])
        await callback.answer("🔄 Обновляю из API...")
        
        from db_utils import get_session, get_event_by_id, update_event_results_from_api
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            if not event:
                await callback.answer("❌ Турнир не найден", show_alert=True)
                return
            
            success = await update_event_results_from_api(session, event)
            
            if success:
                text = (
                    f"✅ <b>Турнир обновлен из API!</b>\n\n"
                    f"<b>{event.title}</b>\n"
                    f"Результаты успешно загружены.\n\n"
                    f"Теперь можно закрыть турнир."
                )
                
                buttons = [
                    [InlineKeyboardButton(text="🏁 Закрыть турнир", callback_data=f"admin_confirm_close:{event_id}")],
                    [InlineKeyboardButton(text="↩️ Назад к списку", callback_data="admin_close_event")]
                ]
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            else:
                text = (
                    f"❌ <b>Не удалось обновить из API</b>\n\n"
                    f"<b>{event.title}</b>\n"
                    f"API не вернул результатов или произошла ошибка.\n\n"
                    f"Можно закрыть турнир вручную."
                )
                
                buttons = [
                    [InlineKeyboardButton(text="🏁 Закрыть вручную", callback_data=f"admin_confirm_close:{event_id}")],
                    [InlineKeyboardButton(text="↩️ Назад к списку", callback_data="admin_close_event")]
                ]
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_update_single: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "admin_create_draft")
async def process_create_draft(callback: CallbackQuery):
    """Создание черновика турнира в БД"""
    try:
        await callback.answer("📝 Создаю черновик...")
        
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        user_id = callback.from_user.id
        logger.info(f"Начинаем создание черновика для user_id={user_id}")
        
        user_data = temp_event_data.get(user_id)
        if not user_data:
            logger.error(f"Данные не найдены для user_id={user_id}")
            await callback.message.edit_text(
                "❌ Данные не найдены. Возможно, истекло время ожидания.\n"
                "Пожалуйста, вернитесь в админ-панель и попробуйте снова.",
                reply_markup=get_admin_menu()
            )
            return
        
        event_data = user_data.get('event')
        fights_data = user_data.get('fights')
        
        if not event_data or not fights_data:
            logger.error(f"Неполные данные для user_id={user_id}")
            await callback.message.edit_text(
                "❌ Ошибка: неполные данные о турнире.",
                reply_markup=get_admin_menu()
            )
            return
        
        logger.info(f"Создаю турнир: {event_data.get('name')} с {len(fights_data)} боями")
        
        # Создаем турнир
        async with get_session() as session:
            event = await create_event_from_api(session, event_data, fights_data)
            
            if event:
                # Очищаем временные данные
                if user_id in temp_event_data:
                    del temp_event_data[user_id]
                
                text = (
                    f"✅ <b>Турнир создан!</b>\n\n"
                    f"🏆 <b>{event.title}</b>\n"
                    f"🆔 <b>ID:</b> {event.id}\n"
                    f"📅 <b>Дата:</b> {event.date_utc.strftime('%d.%m.%Y %H:%M')} UTC\n"
                    f"📊 <b>Статус:</b> {event.status}\n"
                    f"🥊 <b>Боев:</b> {len(fights_data)}\n\n"
                    f"<i>Турнир находится в статусе 'черновик'. Теперь можно ввести коэффициенты.</i>"
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📥 Ввести коэффициенты", callback_data="admin_add_odds")],
                    [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_status")]
                ])
                
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
                logger.info(f"✅ Создан турнир ID: {event.id}")
                
            else:
                logger.error("Не удалось создать турнир")
                await callback.message.edit_text(
                    "❌ Не удалось создать турнир в базе данных.\n"
                    "Проверьте логи для деталей.",
                    reply_markup=get_admin_menu()
                )
                
    except Exception as e:
        logger.error(f"Ошибка создания черновика: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ <b>Критическая ошибка:</b>\n\n"
            f"{str(e)[:200]}\n\n"
            f"Пожалуйста, попробуйте снова.",
            reply_markup=get_admin_menu(),
            parse_mode="HTML"
        )


@dp.callback_query(lambda c: c.data.startswith("admin_input_odds:"))
async def process_input_odds(callback: CallbackQuery):
    """Начало ввода коэффициентов"""
    try:
        await callback.answer("📝 Готовлю форму ввода...")
        logger.info(f"Обработка admin_input_odds, данные: {callback.data}")
        
        event_id = int(callback.data.split(":")[1])
        logger.info(f"Event ID: {event_id}")
        
        from db_utils import get_fights_for_event, get_session
        
        async with get_session() as session:
            fights = await get_fights_for_event(session, event_id)
            logger.info(f"Получено боев: {len(fights)}")
            
            if not fights:
                await callback.message.edit_text(
                    "❌ <b>Ошибка:</b> Не найдены бои для этого турнира.",
                    parse_mode="HTML"
                )
                return
            
            # Формируем список ВСЕХ боев с нумерацией
            fights_list = ""
            for i, fight in enumerate(fights, 1):
                fights_list += f"{i}. {fight.fighter1_name} vs {fight.fighter2_name}\n"
            
            # Формируем пример ввода С НУМЕРАЦИЕЙ СТРОК
            example_lines = []
            for i in range(1, min(4, len(fights) + 1)):  # Пример для первых 3 боев
                # Разные примеры коэффициентов для наглядности
                if i == 1:
                    example_lines.append(f"{i}. 1.45 2.75")
                elif i == 2:
                    example_lines.append(f"{i}. 1.80 2.05")
                else:
                    example_lines.append(f"{i}. 1.65 2.25")
            
            example = "\n".join(example_lines)
            if len(fights) > 3:
                example += f"\n... и ещё {len(fights) - 3} строк"
            
            text = (
                f"📝 <b>Ввод коэффициентов</b>\n\n"
                f"Турнир ID: <b>{event_id}</b>\n"
                f"Всего боев: <b>{len(fights)}</b>\n\n"
                f"<b>Список боев:</b>\n"
                f"{fights_list}\n"
                f"<b>Инструкция:</b>\n"
                f"• Вводите построчно, в том же порядке!\n"
                f"• Одна строка = один бой\n"
                f"• Формат: <code>НОМЕР. КОЭФ1 КОЭФ2</code>\n"
                f"• <b>Номер строки обязателен!</b>\n\n"
                f"<b>Пример для первых {min(3, len(fights))} боев:</b>\n"
                f"<code>{example}</code>\n\n"
                f"<b>Отправьте {len(fights)} строк следующим сообщением:</b>"
            )
            
            # Сохраняем event_id во временных данных
            temp_event_data[callback.from_user.id] = {
                'event_id': event_id,
                'fight_count': len(fights),
                'waiting_for_odds': True
            }
            logger.info(f"Сохранены данные для user_id={callback.from_user.id}: fight_count={len(fights)}")
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_add_odds")]
            ])
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            logger.info("Сообщение с инструкцией отправлено")
            
    except Exception as e:
        logger.error(f"Ошибка в process_input_odds: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {str(e)[:50]}", show_alert=True)
        await callback.message.edit_text(
            f"❌ <b>Ошибка:</b> {str(e)[:200]}",
            reply_markup=get_admin_menu(),
            parse_mode="HTML"
        )

@dp.message(Command("cleardb"))
async def cmd_clear_db(message: Message):
    """Полная очистка ТЕСТОВОЙ БД (только админ)"""
    if message.from_user.id != config.ADMIN_ID:
        return
    
    await message.answer(f"🗑️ Очищаю ТЕСТОВУЮ базу данных ({config.DB_NAME})...")
    
    from database import engine, Base
    import asyncio
    
    async def clear_all():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    
    await clear_all()
    await message.answer(f"✅ Тестовая база данных полностью очищена и пересоздана")

@dp.callback_query(lambda c: c.data.startswith("make_bets:"))
async def process_make_bets_start(callback: CallbackQuery):
    """Начало процесса ставок - выбор 5 основных боев"""
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer()
        
        from db_utils import get_session, get_fights_for_event, get_event_by_id
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.state import State, StatesGroup
        
        # Определяем состояния для процесса ставок
        class BettingStates(StatesGroup):
            choosing_main_fights = State()  # Выбор 5 основных боев
            choosing_fight_winners = State()  # Выбор победителей в каждом бое
            choosing_insurance_fight = State()  # Выбор страховочного боя
            confirming_bets = State()  # Подтверждение
        
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
                InlineKeyboardButton(text="✅ Подтвердить выбор", callback_data=f"confirm_main:{event_id}"),
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

@dp.callback_query(lambda c: c.data.startswith("select_fight:"))
async def process_select_fight(callback: CallbackQuery):
    """Обработка выбора боя"""
    try:
        await callback.answer()
        
        # Парсим данные
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_id = int(parts[2])
        
        user_id = callback.from_user.id
        
        # Проверяем, есть ли данные для этого пользователя
        if 'betting_data' not in temp_event_data or user_id not in temp_event_data['betting_data']:
            await callback.answer("❌ Сессия устарела. Начните заново.", show_alert=True)
            return
        
        betting_data = temp_event_data['betting_data'][user_id]
        
        # Проверяем, что это правильный турнир
        if betting_data['event_id'] != event_id:
            await callback.answer("❌ Ошибка данных.", show_alert=True)
            return
        
        # Проверяем, не выбран ли уже этот бой
        if fight_id in betting_data['selected_main_fights']:
            # Удаляем бой из выбранных
            betting_data['selected_main_fights'].remove(fight_id)
            action = "удалён"
        else:
            # Проверяем, можно ли добавить ещё бой
            if len(betting_data['selected_main_fights']) >= 5:
                await callback.answer("❌ Можно выбрать только 5 боев!", show_alert=True)
                return
            
            # Добавляем бой
            betting_data['selected_main_fights'].append(fight_id)
            action = "добавлен"
        
        # Обновляем сообщение
        await update_fight_selection_message(callback.message, user_id, event_id)
        
        # Короткое уведомление
        await callback.answer(f"Бой {action} ✓")
        
    except Exception as e:
        logger.error(f"Ошибка в select_fight: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("reset_main:"))
async def process_reset_main(callback: CallbackQuery):
    """Сброс выбранных боев"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        if 'betting_data' in temp_event_data and user_id in temp_event_data['betting_data']:
            temp_event_data['betting_data'][user_id]['selected_main_fights'] = []
        
        await callback.answer("Выбор сброшен")
        await update_fight_selection_message(callback.message, user_id, event_id)
        
    except Exception as e:
        logger.error(f"Ошибка в reset_main: {e}")
        await callback.answer("❌ Ошибка")

async def show_insurance_selection(message: Message, user_id: int, event_id: int):
    """Показывает выбор страховочного боя с сохранением оригинальных номеров"""
    try:
        from db_utils import get_session, get_event_by_id, get_fights_for_event
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            all_fights = await get_fights_for_event(session, event_id)
            
            betting_data = temp_event_data['betting_data'][user_id]
            selected_main_ids = betting_data['selected_main_fights']
            
            # Оставляем только бои, которые НЕ в основных
            available_fights = [f for f in all_fights if f.id not in selected_main_ids]
            
            if not available_fights:
                # Если все бои уже выбраны как основные, предлагаем выбрать из них
                available_fights = all_fights
            
            # Сортируем по оригинальному порядку (fight_order)
            available_fights.sort(key=lambda x: x.fight_order)
            
            text = (
                f"🎯 <b>Сделать ставки: Шаг 3 из 4</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
                f"<b>Выбор страховочного боя</b>\n\n"
                f"Основные ставки сохранены! Теперь выберите 1 страховочный бой.\n\n"
                f"<i>Страховочный бой заменит любую из основных ставок, "
                f"если тот бой отменят или признают несостоявшимся.</i>\n\n"
                f"<b>Доступные бои:</b>"
            )
            
            # Показываем доступные бои с оригинальными номерами
            fights_text = ""
            for fight in available_fights:
                odds1 = f"{fight.odds1:.2f}" if fight.odds1 else "?"
                odds2 = f"{fight.odds2:.2f}" if fight.odds2 else "?"
                fights_text += f"{fight.fight_order}. {fight.fighter1_name} ({odds1}) vs {fight.fighter2_name} ({odds2})\n"
            
            text += f"\n{fights_text}"
            
            # Создаём кнопки для выбора боя
            # Используем оригинальные номера для кнопок
            buttons = []
            row = []
            
            for fight in available_fights:
                btn_text = f"{fight.fight_order}"
                callback_data = f"select_insurance:{event_id}:{fight.id}"
                row.append(InlineKeyboardButton(text=btn_text, callback_data=callback_data))
                
                if len(row) == 3:
                    buttons.append(row)
                    row = []
            
            if row:
                buttons.append(row)
            
            # Кнопки управления
            buttons.append([
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_winners:{event_id}")
            ])
            buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu_current")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в show_insurance_selection: {e}", exc_info=True)

async def show_insurance_winner_selection(message: Message, user_id: int, event_id: int):
    """Выбор победителя в страховочном бою"""
    try:
        from db_utils import get_session, get_event_by_id, get_fights_for_event
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            all_fights = await get_fights_for_event(session, event_id)
            
            betting_data = temp_event_data['betting_data'][user_id]
            insurance_fight_id = betting_data.get('insurance_fight_id')
            
            if not insurance_fight_id:
                await callback.answer("❌ Ошибка: бой не выбран", show_alert=True)
                return
            
            # Находим выбранный бой
            insurance_fight = next((f for f in all_fights if f.id == insurance_fight_id), None)
            
            if not insurance_fight:
                await callback.answer("❌ Ошибка: бой не найден", show_alert=True)
                return
            
            text = (
                f"🎯 <b>Сделать ставки: Шаг 3 из 4</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
                f"<b>Страховочный бой (№{insurance_fight.fight_order}):</b>\n"
                f"<b>{insurance_fight.fighter1_name}</b> (коэф: <b>{insurance_fight.odds1:.2f}</b>) "
                f"vs <b>{insurance_fight.fighter2_name}</b> (коэф: <b>{insurance_fight.odds2:.2f}</b>)\n\n"
                f"<i>На кого ставите в страховочном бою?</i>"
            )
            
            buttons = [
                [
                    InlineKeyboardButton(
                        text=f"👊 {insurance_fight.fighter1_name} ({insurance_fight.odds1:.2f})", 
                        callback_data=f"choose_insurance_winner:{event_id}:{insurance_fight_id}:1"
                    ),
                    InlineKeyboardButton(
                        text=f"🥊 {insurance_fight.fighter2_name} ({insurance_fight.odds2:.2f})", 
                        callback_data=f"choose_insurance_winner:{event_id}:{insurance_fight_id}:2"
                    )
                ],
                [
                    InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_insurance_select:{event_id}")
                ]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в show_insurance_winner_selection: {e}")

async def show_confirmation(message: Message, user_id: int, event_id: int):
    """Показывает подтверждение ставок перед сохранением"""
    try:
        from db_utils import get_session, get_event_by_id, get_fights_for_event
        
        if ('betting_data' not in temp_event_data or 
            user_id not in temp_event_data['betting_data']):
            await message.edit_text(
                "❌ Сессия устарела. Начните заново.",
                reply_markup=get_back_button()
            )
            return
        
        betting_data = temp_event_data['betting_data'][user_id]
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            all_fights = await get_fights_for_event(session, event_id)
            fights_dict = {f.id: f for f in all_fights}
            
            # Формируем текст с итогами
            text = f"🎯 <b>Сделать ставки: Шаг 4 из 4</b>\n\n"
            text += f"🏆 <b>{event.title}</b>\n\n"
            text += "<b>🌟 Основные ставки (5):</b>\n"
            
            total_odds = 1.0
            main_bets_count = 0
            
            # Основные ставки - УЖЕ ОТСОРТИРОВАНЫ по fight_order
            selected_fights = betting_data.get('selected_fights_ordered', [])
            selected_winners = betting_data.get('selected_winners', {})
            
            # Просто выводим в том порядке, в котором они есть (уже отсортированы)
            for i, fight in enumerate(selected_fights, 1):
                fight_id = fight.id
                if fight_id in selected_winners:
                    winner_info = selected_winners[fight_id]
                    chosen_fighter = winner_info.get('chosen_fighter', 1)
                    
                    fighter_name = (fight.fighter1_name if chosen_fighter == 1 
                                   else fight.fighter2_name)
                    odds = fight.odds1 if chosen_fighter == 1 else fight.odds2
                    
                    text += f"{i}. Бой {fight.fight_order}: <b>{fighter_name}</b> (коэф: <b>{odds:.2f}</b>)\n"
                    
                    if odds:
                        total_odds *= float(odds)
                    main_bets_count += 1
            
            # Остальной код без изменений...
            
            # Страховочная ставка
            insurance_fight_id = betting_data.get('insurance_fight_id')
            insurance_winner = betting_data.get('insurance_winner')
            
            if insurance_fight_id and insurance_winner:
                insurance_fight = fights_dict.get(insurance_fight_id)
                if insurance_fight:
                    fighter_name = (insurance_fight.fighter1_name if insurance_winner == 1 
                                   else insurance_fight.fighter2_name)
                    odds = (insurance_fight.odds1 if insurance_winner == 1 
                           else insurance_fight.odds2)
                    
                    text += f"\n🛡️ <b>Страховочная ставка (№{insurance_fight.fight_order}):</b>\n"
                    text += f"Бой {insurance_fight.fight_order}: <b>{fighter_name}</b> (коэф: <b>{odds:.2f}</b>)\n"
            
            # Статистика
            if main_bets_count == 5:
                potential_points = total_odds
                text += f"\n📊 <b>Потенциальный выигрыш:</b> {potential_points:.2f} очков\n"
                text += f"<i>Если все 5 ставок сыграют, вы получите {potential_points:.2f} очков</i>\n"
            else:
                text += f"\n⚠️ <b>Внимание:</b> выбрано только {main_bets_count}/5 основных ставок!\n"
            
            text += f"\n<b>Подтвердить ставки?</b>"
            
            # Кнопки
            buttons = [
                [InlineKeyboardButton(text="✅ Подтвердить и сохранить", callback_data=f"save_bets:{event_id}")],
                [InlineKeyboardButton(text="✏️ Изменить ставки", callback_data=f"make_bets:{event_id}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_current")]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в show_confirmation: {e}", exc_info=True)
        await message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_back_button()
        )

@dp.callback_query(lambda c: c.data.startswith("save_bets:"))
async def process_save_bets(callback: CallbackQuery):
    """Сохранение ставок в БД"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        if ('betting_data' not in temp_event_data or 
            user_id not in temp_event_data['betting_data']):
            await callback.answer("❌ Сессия устарела", show_alert=True)
            return
        
        betting_data = temp_event_data['betting_data'][user_id]
        
        # Проверяем, что все 5 основных ставок выбраны
        selected_fights = betting_data.get('selected_fights_ordered', [])
        selected_winners = betting_data.get('selected_winners', {})
        
        if len(selected_fights) != 5:
            await callback.answer("❌ Нужно выбрать 5 основных ставок!", show_alert=True)
            return
        
        # Проверяем, что для всех выбранных боев есть победители
        for fight in selected_fights:
            if fight.id not in selected_winners:
                await callback.answer("❌ Не для всех боев выбран победитель!", show_alert=True)
                return
        
        await callback.answer("💾 Сохраняю ставки...")
        
        from db_utils import get_session, save_user_bets
        
        # Подготавливаем данные для сохранения
        bets_to_save = {
            'main_bets': [],
            'insurance_bet': None
        }
        
        # Основные ставки
        for fight in selected_fights:
            winner_info = selected_winners[fight.id]
            chosen_fighter = winner_info['chosen_fighter']
            odds = fight.odds1 if chosen_fighter == 1 else fight.odds2
            
            bets_to_save['main_bets'].append({
                'fight_id': fight.id,
                'chosen_fighter': chosen_fighter,
                'odds': odds
            })
        
        # Страховочная ставка (если есть)
        insurance_fight_id = betting_data.get('insurance_fight_id')
        insurance_winner = betting_data.get('insurance_winner')
        
        if insurance_fight_id and insurance_winner:
            # Находим бой
            from db_utils import get_fights_for_event
            async with get_session() as session:
                all_fights = await get_fights_for_event(session, event_id)
                insurance_fight = next((f for f in all_fights if f.id == insurance_fight_id), None)
                
                if insurance_fight:
                    odds = (insurance_fight.odds1 if insurance_winner == 1 
                           else insurance_fight.odds2)
                    
                    bets_to_save['insurance_bet'] = {
                        'fight_id': insurance_fight_id,
                        'chosen_fighter': insurance_winner,
                        'odds': odds
                    }
        
        # Сохраняем в БД
        async with get_session() as session:
            success = await save_user_bets(
                session, 
                user_id, 
                event_id, 
                bets_to_save,
                username=callback.from_user.username,  # ДОБАВИТЬ
                full_name=callback.from_user.full_name  # ДОБАВИТЬ
            )
            
            if success:
                # Очищаем временные данные
                if 'betting_data' in temp_event_data and user_id in temp_event_data['betting_data']:
                    del temp_event_data['betting_data'][user_id]
                
                # Показываем успешное сообщение
                await callback.message.edit_text(
                    "✅ <b>Ваши ставки успешно сохранены!</b>\n\n"
                    "Теперь ждите результатов турнира. Удачи! 🍀\n\n"
                    "Вы можете изменить свои ставки в любое время до начала турнира.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📊 Мои ставки", callback_data=f"my_bets_detail:{event_id}")],
                        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_current")]
                    ]),
                    parse_mode="HTML"
                )
                logger.info(f"Сохранены ставки для user_id={user_id} на event_id={event_id}")
            else:
                await callback.message.edit_text(
                    "❌ <b>Ошибка сохранения ставок.</b>\n"
                    "Попробуйте еще раз или обратитесь к администратору.",
                    reply_markup=get_back_button(),
                    parse_mode="HTML"
                )
                
    except Exception as e:
        logger.error(f"Ошибка сохранения ставок: {e}", exc_info=True)
        await callback.answer("❌ Ошибка сохранения", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("select_insurance:"))
async def process_select_insurance(callback: CallbackQuery):
    """Выбор страховочного боя"""
    try:
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_id = int(parts[2])
        
        user_id = callback.from_user.id
        
        if ('betting_data' not in temp_event_data or 
            user_id not in temp_event_data['betting_data']):
            await callback.answer("❌ Сессия устарела", show_alert=True)
            return
        
        betting_data = temp_event_data['betting_data'][user_id]
        
        # Сохраняем выбранный страховочный бой
        betting_data['insurance_fight_id'] = fight_id
        betting_data['step'] = 'insurance_selected'
        
        await callback.answer("Бой выбран! Теперь выберите победителя.")
        
        # Показываем выбор победителя в страховочном бою
        await show_insurance_winner_selection(callback.message, user_id, event_id)
        
    except Exception as e:
        logger.error(f"Ошибка в select_insurance: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("back_to_fight:"))
async def process_back_to_fight(callback: CallbackQuery):
    """Возврат к предыдущему бою"""
    try:
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_index = max(0, int(parts[2]) - 1)  # Возвращаемся на один назад
        
        user_id = callback.from_user.id
        
        await callback.answer()
        await show_fight_winner_selection(callback.message, user_id, event_id, fight_index)
        
    except Exception as e:
        logger.error(f"Ошибка в back_to_fight: {e}")
        await callback.answer("❌ Ошибка")

@dp.callback_query(lambda c: c.data.startswith("choose_insurance_winner:"))
async def process_choose_insurance_winner(callback: CallbackQuery):
    """Выбор победителя в страховочном бою"""
    try:
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_id = int(parts[2])
        chosen_fighter = int(parts[3])  # 1 или 2
        
        user_id = callback.from_user.id
        
        if ('betting_data' not in temp_event_data or 
            user_id not in temp_event_data['betting_data']):
            await callback.answer("❌ Сессия устарела", show_alert=True)
            return
        
        betting_data = temp_event_data['betting_data'][user_id]
        
        # Сохраняем выбор
        betting_data['insurance_winner'] = chosen_fighter
        betting_data['step'] = 'insurance_complete'
        
        # Получаем имя бойца для уведомления
        from db_utils import get_session, get_fights_for_event
        
        async with get_session() as session:
            fights = await get_fights_for_event(session, event_id)
            fight = next((f for f in fights if f.id == fight_id), None)
            
            if fight:
                fighter_name = fight.fighter1_name if chosen_fighter == 1 else fight.fighter2_name
                odds = fight.odds1 if chosen_fighter == 1 else fight.odds2
                await callback.answer(f"✅ Страховка: {fighter_name} ({odds:.2f})")
            else:
                await callback.answer("✅ Страховочная ставка сохранена")
        
        # Переходим к подтверждению (ВОТ ЗДЕСЬ ИЗМЕНЕНИЕ!)
        await show_confirmation(callback.message, user_id, event_id)
        
    except Exception as e:
        logger.error(f"Ошибка в choose_insurance_winner: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("back_to_winners:"))
async def process_back_to_winners(callback: CallbackQuery):
    """Возврат к выбору победителей"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        if ('betting_data' not in temp_event_data or 
            user_id not in temp_event_data['betting_data']):
            await callback.answer("❌ Сессия устарела", show_alert=True)
            return
        
        betting_data = temp_event_data['betting_data'][user_id]
        
        # Возвращаемся к последнему основному бою
        last_index = len(betting_data['selected_fights_ordered']) - 1
        await show_fight_winner_selection(callback.message, user_id, event_id, last_index)
        
    except Exception as e:
        logger.error(f"Ошибка в back_to_winners: {e}")

@dp.callback_query(lambda c: c.data.startswith("back_to_insurance_select:"))
async def process_back_to_insurance_select(callback: CallbackQuery):
    """Возврат к выбору страховочного боя"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        await callback.answer()
        await show_insurance_selection(callback.message, user_id, event_id)
        
    except Exception as e:
        logger.error(f"Ошибка в back_to_insurance_select: {e}")
        
@dp.callback_query(lambda c: c.data.startswith("choose_winner:"))
async def process_choose_winner(callback: CallbackQuery):
    """Обработка выбора победителя в бою"""
    try:
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_id = int(parts[2])
        chosen_fighter = int(parts[3])  # 1 или 2
        
        user_id = callback.from_user.id
        
        if ('betting_data' not in temp_event_data or 
            user_id not in temp_event_data['betting_data']):
            await callback.answer("❌ Сессия устарела", show_alert=True)
            return
        
        betting_data = temp_event_data['betting_data'][user_id]
        
        # Сохраняем выбор
        if 'selected_winners' not in betting_data:
            betting_data['selected_winners'] = {}
        
        betting_data['selected_winners'][fight_id] = {
            'chosen_fighter': chosen_fighter,
            'fight_id': fight_id
        }
        
        # Находим коэффициент для выбранного бойца
        from db_utils import get_session, get_fights_for_event
        
        async with get_session() as session:
            fights = await get_fights_for_event(session, event_id)
            fight = next((f for f in fights if f.id == fight_id), None)
            
            if fight:
                odds = fight.odds1 if chosen_fighter == 1 else fight.odds2
                fighter_name = fight.fighter1_name if chosen_fighter == 1 else fight.fighter2_name
                await callback.answer(f"✅ Выбрано: {fighter_name} ({odds:.2f})")
            else:
                await callback.answer("✅ Выбор сохранен")
        
        # Переходим к следующему бою
        current_index = betting_data['current_fight_index']
        next_index = current_index + 1
        
        await show_fight_winner_selection(callback.message, user_id, event_id, next_index)
        
    except Exception as e:
        logger.error(f"Ошибка в choose_winner: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

async def show_fight_winner_selection(message: Message, user_id: int, event_id: int, fight_index: int):
    """Показывает выбор победителя для конкретного боя"""
    try:
        from db_utils import get_session, get_event_by_id
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            betting_data = temp_event_data['betting_data'][user_id]
            
            if fight_index >= len(betting_data['selected_fights_ordered']):
                # Все бои пройдены, переходим к страховке
                await show_insurance_selection(message, user_id, event_id)
                return
            
            fight = betting_data['selected_fights_ordered'][fight_index]
            
            # Обновляем текущий индекс
            betting_data['current_fight_index'] = fight_index
            
            text = (
                f"🎯 <b>Сделать ставки: Шаг 2 из 4</b>\n\n"
                f"🏆 <b>{event.title}</b>\n\n"
                f"<b>Бой {fight_index + 1} из 5</b>\n"
                f"<b>{fight.fighter1_name}</b> (коэф: <b>{fight.odds1:.2f}</b>) "
                f"vs <b>{fight.fighter2_name}</b> (коэф: <b>{fight.odds2:.2f}</b>)\n\n"
                f"<i>На кого ставите?</i>"
            )
            
            buttons = [
                [
                    InlineKeyboardButton(
                        text=f"👊 {fight.fighter1_name} ({fight.odds1:.2f})", 
                        callback_data=f"choose_winner:{event_id}:{fight.id}:1"
                    ),
                    InlineKeyboardButton(
                        text=f"🥊 {fight.fighter2_name} ({fight.odds2:.2f})", 
                        callback_data=f"choose_winner:{event_id}:{fight.id}:2"
                    )
                ],
                [
                    InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_fight:{event_id}:{fight_index}"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="menu_current")
                ]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка в show_fight_winner_selection: {e}")

@dp.callback_query(lambda c: c.data.startswith("confirm_main:"))
async def process_confirm_main(callback: CallbackQuery):
    """Переход к выбору победителей"""
    try:
        event_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        # Проверяем данные
        if ('betting_data' not in temp_event_data or 
            user_id not in temp_event_data['betting_data']):
            await callback.answer("❌ Сессия устарела", show_alert=True)
            return
        
        betting_data = temp_event_data['betting_data'][user_id]
        
        if len(betting_data['selected_main_fights']) != 5:
            await callback.answer("❌ Нужно выбрать 5 боев!", show_alert=True)
            return
        
        await callback.answer("Загружаю бои...")
        
        from db_utils import get_session, get_fights_for_event, get_event_by_id
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            all_fights = await get_fights_for_event(session, event_id)
            
            # Создаём словарь боев для быстрого поиска
            fights_dict = {fight.id: fight for fight in all_fights}
            
            # Получаем выбранные бои
            selected_fights = []
            for fight_id in betting_data['selected_main_fights']:
                if fight_id in fights_dict:
                    selected_fights.append(fights_dict[fight_id])
            
            # ВАЖНО: СОРТИРУЕМ по fight_order (исправление!)
            selected_fights.sort(key=lambda f: f.fight_order)
            
            # Сохраняем ОТСОРТИРОВАННЫЕ бои
            betting_data['selected_fights_ordered'] = selected_fights
            betting_data['current_fight_index'] = 0  # Начинаем с первого боя
            betting_data['step'] = 'choosing_winners'
            
            # Показываем первый бой для выбора победителя
            await show_fight_winner_selection(callback.message, user_id, event_id, 0)
        
    except Exception as e:
        logger.error(f"Ошибка в confirm_main: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@dp.callback_query(lambda c: c.data == "admin_close_event")
async def process_admin_close_event(callback: CallbackQuery):
    """Закрытие турнира - выбор из списка"""
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        await callback.answer("🏁 Выбор турнира для закрытия")
        
        from db_utils import get_session, get_unfinished_events
        from database import Event, Fight
        from sqlalchemy import select
        
        async with get_session() as session:
            # Получаем незавершенные турниры
            unfinished_events = await get_unfinished_events(session)
            
            if not unfinished_events:
                text = (
                    "🏁 <b>Закрытие турнира</b>\n\n"
                    "Нет турниров для закрытия.\n"
                    "Все турниры уже завершены или пока нет активных."
                )
                keyboard = get_admin_menu()
            else:
                text = "🏁 <b>Выберите турнир для закрытия:</b>\n\n"
                
                buttons = []
                for event in unfinished_events:
                    # Получаем статистику по боям
                    fights_result = await session.execute(
                        select(Fight).where(Fight.event_id == event.id)
                    )
                    fights = fights_result.scalars().all()
                    
                    # Считаем бои с результатами и без
                    total_fights = len(fights)
                    finished_fights = sum(1 for f in fights if f.winner is not None)
                    
                    btn_text = (
                        f"{event.short_title} ({event.date_utc.strftime('%d.%m')}) - "
                        f"{finished_fights}/{total_fights} боев"
                    )
                    
                    buttons.append([
                        InlineKeyboardButton(
                            text=btn_text,
                            callback_data=f"admin_confirm_close:{event.id}"
                        )
                    ])
                
                buttons.append([
                    InlineKeyboardButton(text="🔄 Обновить все автоматически", callback_data="admin_update_all")
                ])
                buttons.append([
                    InlineKeyboardButton(text="↩️ Назад", callback_data="admin_status")
                ])
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_close_event: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("admin_confirm_close:"))
async def process_admin_confirm_close(callback: CallbackQuery):
    """Подтверждение закрытия турнира"""
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        event_id = int(callback.data.split(":")[1])
        
        from db_utils import get_session, get_event_by_id, get_fights_for_event, update_event_results_from_api
        from database import Event, Fight
        from sqlalchemy import select
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            if not event:
                await callback.answer("❌ Турнир не найден", show_alert=True)
                return
            
            # Получаем бои
            fights = await get_fights_for_event(session, event_id)
            
            # Считаем статистику
            total_fights = len(fights)
            finished_fights = sum(1 for f in fights if f.winner is not None)
            unfinished_fights = total_fights - finished_fights
            
            text = (
                f"🏁 <b>Подтверждение закрытия турнира</b>\n\n"
                f"<b>{event.title}</b>\n"
                f"Дата: {event.date_utc.strftime('%d.%m.%Y')}\n"
                f"Статус: {event.status}\n\n"
                f"<b>Статистика боев:</b>\n"
                f"• Всего боев: {total_fights}\n"
                f"• С результатами: {finished_fights}\n"
                f"• Без результатов: {unfinished_fights}\n\n"
            )
            
            if unfinished_fights > 0:
                text += (
                    f"⚠️ <b>Внимание!</b> {unfinished_fights} боев без результатов.\n"
                    f"При закрытии им будут присвоены результаты 'nc' (не состоялся).\n\n"
                )
            
            text += "Вы уверены, что хотите закрыть турнир?"
            
            buttons = [
                [
                    InlineKeyboardButton(
                        text="✅ Да, закрыть турнир", 
                        callback_data=f"admin_execute_close:{event_id}"
                    ),
                    InlineKeyboardButton(
                        text="🔄 Сначала обновить из API", 
                        callback_data=f"admin_update_single:{event_id}"
                    )
                ],
                [
                    InlineKeyboardButton(text="❌ Нет, отмена", callback_data="admin_close_event")
                ]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_confirm_close: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("admin_update_single:"))
async def process_admin_update_single(callback: CallbackQuery):
    """Обновление одного турнира из API"""
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        event_id = int(callback.data.split(":")[1])
        await callback.answer("🔄 Обновляю из API...")
        
        from db_utils import get_session, get_event_by_id, update_event_results_from_api
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            if not event:
                await callback.answer("❌ Турнир не найден", show_alert=True)
                return
            
            success = await update_event_results_from_api(session, event)
            
            if success:
                text = (
                    f"✅ <b>Турнир обновлен из API!</b>\n\n"
                    f"<b>{event.title}</b>\n"
                    f"Результаты успешно загружены.\n\n"
                    f"Теперь можно закрыть турнир."
                )
                
                buttons = [
                    [InlineKeyboardButton(text="🏁 Закрыть турнир", callback_data=f"admin_confirm_close:{event_id}")],
                    [InlineKeyboardButton(text="↩️ Назад к списку", callback_data="admin_close_event")]
                ]
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            else:
                text = (
                    f"❌ <b>Не удалось обновить из API</b>\n\n"
                    f"<b>{event.title}</b>\n"
                    f"API не вернул результатов или произошла ошибка.\n\n"
                    f"Можно закрыть турнир вручную."
                )
                
                buttons = [
                    [InlineKeyboardButton(text="🏁 Закрыть вручную", callback_data=f"admin_confirm_close:{event_id}")],
                    [InlineKeyboardButton(text="↩️ Назад к списку", callback_data="admin_close_event")]
                ]
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_update_single: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("admin_calculate_points:"))
async def process_admin_calculate_points(callback: CallbackQuery):
    """Расчет очков для турнира"""
    try:
        if callback.from_user.id != config.ADMIN_ID:
            await callback.answer("⛔ Нет доступа!", show_alert=True)
            return
        
        event_id = int(callback.data.split(":")[1])
        await callback.answer("🧮 Считаю очки...")
        
        from db_utils import get_session, get_event_by_id, calculate_user_points_for_event
        from database import User, Bet
        from sqlalchemy import select
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            if not event:
                await callback.answer("❌ Турнир не найден", show_alert=True)
                return
            
            # Получаем всех пользователей
            users_result = await session.execute(select(User))
            all_users = users_result.scalars().all()
            
            if not all_users:
                await callback.message.edit_text(
                    "❌ Нет пользователей для расчета очков",
                    reply_markup=get_admin_menu()
                )
                return
            
            # Считаем очки для каждого пользователя
            results = []
            for user in all_users:
                points = await calculate_user_points_for_event(session, user.user_id, event_id)
                results.append({
                    'user': user,
                    'points': points
                })
            
            # Сортируем по очкам (по убыванию)
            results.sort(key=lambda x: x['points'], reverse=True)
            
            # Формируем текст с результатами
            text = f"📊 <b>Результаты турнира: {event.title}</b>\n\n"
            
            for i, result in enumerate(results, 1):
                user = result['user']
                points = result['points']
                
                username = user.username or user.full_name or f"Игрок {user.user_id}"
                medal = ""
                if i == 1:
                    medal = "🥇"
                elif i == 2:
                    medal = "🥈"
                elif i == 3:
                    medal = "🥉"
                
                text += f"{medal} <b>{i}. {username}:</b> {points:.2f} очков\n"
            
            # Обновляем общий баланс пользователей
            for result in results:
                user = result['user']
                points = result['points']
                
                # Добавляем очки к общему балансу - КОРРЕКТНЫЕ ТИПЫ
                if user.total_balance is None:
                    user.total_balance = 0.0
                else:
                    # Приводим к float чтобы избежать проблем с Decimal
                    user.total_balance = float(user.total_balance)
                
                user.total_balance += float(points)
            
            await session.commit()
            
            text += f"\n✅ <b>Очки рассчитаны и добавлены к общему балансу!</b>"
            
            # Кнопки
            buttons = [
                [InlineKeyboardButton(text="📊 Посмотреть архив", callback_data=f"view_archive:{event_id}")],
                [InlineKeyboardButton(text="📈 Общий рейтинг", callback_data="menu_rating")],
                [InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_status")]
            ]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка расчета очков: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ <b>Ошибка расчета очков:</b>\n{str(e)[:200]}",
            reply_markup=get_admin_menu(),
            parse_mode="HTML"
        )



# ==================== ОБРАБОТКА СООБЩЕНИЙ ====================

@dp.message()
async def handle_all_messages(message: Message):
    """Обработка всех сообщений"""
    user_id = message.from_user.id
    
    # Проверяем, ожидаем ли мы коэффициенты от этого пользователя
    user_data = temp_event_data.get(user_id)
    
    if user_data and user_data.get('waiting_for_odds') and user_id == config.ADMIN_ID:
        # Это админ вводит коэффициенты
        event_id = user_data['event_id']
        expected_count = user_data['fight_count']
        
        logger.info(f"Админ вводит коэффициенты для event_id={event_id}, ожидаем {expected_count} строк")
        
        try:
            # Парсим ввод
            lines = [line.strip() for line in message.text.strip().split('\n') if line.strip()]
            
            # Проверяем количество строк
            if len(lines) != expected_count:
                await message.answer(
                    f"❌ <b>Неверное количество строк!</b>\n\n"
                    f"Ожидалось: {expected_count} строк (по одной на каждый бой)\n"
                    f"Получено: {len(lines)} строк\n\n"
                    f"Пожалуйста, введите заново:",
                    parse_mode="HTML"
                )
                return
            
            # Получаем список боев из БД чтобы знать их ID
            async with get_session() as session:
                fights = await get_fights_for_event(session, event_id)
                
                if len(fights) != expected_count:
                    await message.answer(
                        f"❌ <b>Ошибка данных!</b>\n\n"
                        f"В базе {len(fights)} боев, а ожидали {expected_count}.\n"
                        f"Пожалуйста, начните заново.",
                        parse_mode="HTML"
                    )
                    temp_event_data.pop(user_id, None)
                    return
                
                # Парсим коэффициенты и связываем с ID боев
                odds_list = []
                errors = []
                
                for i, (line, fight) in enumerate(zip(lines, fights), 1):
                    try:
                        parts = line.split()
                        
                        # Поддержка двух форматов:
                        # 1. С нумерацией: "1. 1.45 2.75" (3 части)
                        # 2. Без нумерации: "1.45 2.75" (2 части) - для обратной совместимости
                        
                        if len(parts) == 3:
                            # Формат с нумерацией: "1. 1.45 2.75" или "1 1.45 2.75"
                            num_part, odds1_str, odds2_str = parts
                            
                            # Убираем точку после номера если есть
                            if num_part.endswith('.'):
                                num_part = num_part[:-1]
                            
                            # Проверяем что номер строки совпадает с ожидаемым
                            try:
                                line_num = int(num_part)
                                if line_num != i:
                                    errors.append(f"Строка {i}: неверный номер строки (ожидалось {i}, получено {num_part})")
                                    continue
                            except ValueError:
                                errors.append(f"Строка {i}: некорректный номер '{num_part}'")
                                continue
                                
                        elif len(parts) == 2:
                            # Формат без нумерации: "1.45 2.75" (старый вариант)
                            odds1_str, odds2_str = parts
                        else:
                            errors.append(f"Строка {i}: должно быть 2 или 3 числа (получено {len(parts)})")
                            continue
                        
                        # Парсим коэффициенты
                        odds1 = float(odds1_str)
                        odds2 = float(odds2_str)
                        
                        # Проверяем валидность коэффициентов
                        if odds1 <= 0 or odds2 <= 0:
                            errors.append(f"Строка {i}: коэффициенты должны быть больше 0")
                            continue
                        
                        if odds1 < 1.0 or odds2 < 1.0:
                            errors.append(f"Строка {i}: коэффициенты должны быть не менее 1.0")
                            continue
                        
                        # Сохраняем с ID боя
                        odds_list.append((fight.id, odds1, odds2))
                        
                    except ValueError as ve:
                        if "could not convert string to float" in str(ve):
                            errors.append(f"Строка {i}: некорректное число (используйте точку как разделитель)")
                        else:
                            errors.append(f"Строка {i}: ошибка формата ({str(ve)[:30]})")
                
                # Если есть ошибки — показываем их
                if errors:
                    error_text = "\n".join(errors[:10])  # Показываем до 10 ошибок
                    if len(errors) > 10:
                        error_text += f"\n... и ещё {len(errors) - 10} ошибок"
                    
                    # Подсказка по формату
                    format_example = "1. 1.45 2.75\n2. 1.80 2.05\n3. 1.65 2.25"
                    
                    await message.answer(
                        f"❌ <b>Обнаружены ошибки:</b>\n\n{error_text}\n\n"
                        f"<b>Правильный формат:</b>\n"
                        f"<code>{format_example}</code>\n\n"
                        f"Можно также без нумерации:\n"
                        f"<code>1.45 2.75\n1.80 2.05\n1.65 2.25</code>\n\n"
                        f"Введите заново:",
                        parse_mode="HTML"
                    )
                    return
                
                # Сохраняем в БД
                success = await update_fight_odds_batch(session, event_id, odds_list)
                
                if success:
                    # Открываем турнир для ставок
                    await open_event_for_bets(session, event_id)
                    
                    await message.answer(
                        f"✅ <b>Коэффициенты успешно сохранены!</b>\n\n"
                        f"Турнир открыт для ставок игроков.\n"
                        f"Игроки теперь могут делать ставки через меню '🥊 Текущий турнир'.",
                        reply_markup=get_admin_menu(),
                        parse_mode="HTML"
                    )
                    logger.info(f"Коэффициенты сохранены для турнира {event_id}")
                else:
                    await message.answer(
                        "❌ <b>Ошибка сохранения коэффициентов.</b>\n"
                        "Возможно, проблема с базой данных.",
                        reply_markup=get_admin_menu(),
                        parse_mode="HTML"
                    )
            
            # Очищаем временные данные
            temp_event_data.pop(user_id, None)
            
        except Exception as e:
            logger.error(f"Ошибка обработки коэффициентов: {e}", exc_info=True)
            await message.answer(
                f"❌ <b>Критическая ошибка:</b> {str(e)[:200]}",
                reply_markup=get_admin_menu(),
                parse_mode="HTML"
            )
            temp_event_data.pop(user_id, None)
    
    else:
        # Обычное сообщение
        if message.text:
            await message.answer(
                "🤖 Используй кнопки меню для навигации.\n"
                "Или напиши /start для перезапуска бота.",
                reply_markup=get_main_menu()
            )

from aiogram.types import BotCommand, BotCommandScopeDefault

# -----------------------
# Установка команд в меню бота
# -----------------------
async def set_bot_commands():
    """
    Устанавливает команды бота, которые будут видны в меню
    """
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="admin", description="⚙️ Админ-панель"),
        BotCommand(command="cleardb", description="🗑️ Очистить БД (только админ)"),
    ]
    
    await bot.set_my_commands(commands)  # <-- используем глобальный bot
    logger.info("Команды бота установлены в меню")

# ==================== ЗАПУСК БОТА ====================

async def main():
    """Основная функция запуска бота"""
    logger.info("=" * 50)
    logger.info("ЗАПУСК UFC БОТА...")
    logger.info(f"Admin ID: {config.ADMIN_ID}")
    logger.info("=" * 50)
    
    try:
        # 1. Устанавливаем команды в меню бота
        await set_bot_commands()
        logger.info("✅ Команды бота установлены")
        
        # 2. Создаем таблицы БД
        await create_tables()
        logger.info("✅ База данных готова")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        return
    
    # 3. Запускаем бота
    try:
        logger.info("✅ Бот запущен и готов к работе")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("ЭСУКАБЛЯ!")
    except KeyboardInterrupt:
        logger.info("Бот остановлен")