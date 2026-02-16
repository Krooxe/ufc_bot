"""
Админ-панель UFC бота
Управление турнирами: создание, редактирование коэффициентов, закрытие
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from decimal import Decimal

import config
from utils.keyboards import get_admin_menu, get_back_button
from utils.states import temp_event_data

logger = logging.getLogger(__name__)

router = Router()


# ============ ГЛАВНОЕ МЕНЮ АДМИНКИ ============

@router.callback_query(lambda c: c.data.startswith("admin_") and c.data not in [
    "admin_announce", "admin_close_event", "admin_create_draft", 
    "admin_create_from_api", "admin_create_manual", "admin_add_odds"  # ← Добавил в исключения
] and not any(c.data.startswith(prefix) for prefix in [
    "admin_input_odds:",
    "admin_edit_odds:",
    "admin_open_betting:",
    "admin_confirm_close:",
    "admin_execute_close:",
    "admin_update_single:",
    "admin_calculate_points:",
    "admin_set_winner:",
]))
async def process_admin_commands(callback: CallbackQuery):
    """Обработка админских команд (главное меню админки)"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    command = callback.data
    
    try:
        if command == "admin_new_ppv":
            # Создание нового PPV турнира
            await callback.answer()
            await show_create_ppv_menu(callback)
            
        elif command == "admin_status":
            # Показ статуса системы
            await callback.answer()
            await show_system_status(callback)
            
        else:
            await callback.answer("Функция в разработке", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка в admin_commands: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ============ ВЫБОР СПОСОБА СОЗДАНИЯ ТУРНИРА ============

@router.callback_query(lambda c: c.data == "admin_create_from_api")
async def process_create_from_api(callback: CallbackQuery):
    """Создание турнира из UFC API"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.answer("🔄 Загружаю данные из UFC API...")
    
    try:
        from api import get_next_ppv_event
        
        # Получаем данные из API
        event_data = await get_next_ppv_event()
        
        if not event_data:
            await callback.message.edit_text(
                "❌ Не удалось получить данные из UFC API.\n\n"
                "Возможные причины:\n"
                "• Нет предстоящих PPV турниров\n"
                "• Проблемы с доступом к API\n\n"
                "Попробуйте создать турнир вручную.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_new_ppv")]
                ]),
                parse_mode="HTML"
            )
            return
        
        # Сохраняем данные во временное хранилище
        user_id = callback.from_user.id
        temp_event_data[user_id] = event_data
        
        event = event_data.get('event', {})
        fights = event_data.get('fights', [])
        
        text = (
            f"📋 <b>Предпросмотр турнира</b>\n\n"
            f"🏆 <b>{event.get('name', 'Без названия')}</b>\n"
            f"📅 <b>Дата:</b> {event.get('date', 'Не указана')}\n"
            f"🥊 <b>Боев:</b> {len(fights)}\n\n"
            f"<b>Создать этот турнир?</b>"
        )
        
        buttons = [
            [InlineKeyboardButton(text="✅ Создать турнир", callback_data="admin_create_draft")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_new_ppv")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка создания из API: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_admin_menu()
        )


@router.callback_query(lambda c: c.data == "admin_create_manual")
async def process_create_manual(callback: CallbackQuery):
    """Ручное создание турнира (будущий функционал)"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.answer()
    
    text = (
        "📝 <b>Ручное создание турнира</b>\n\n"
        "Эта функция пока в разработке.\n\n"
        "Сейчас доступно только создание через UFC API.\n\n"
        "Хотите попробовать загрузить турнир из API?"
    )
    
    buttons = [
        [InlineKeyboardButton(text="🌐 Загрузить из API", callback_data="admin_create_from_api")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_new_ppv")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# ============ СОЗДАНИЕ ТУРНИРА ============

async def show_create_ppv_menu(callback: CallbackQuery):
    """Меню создания PPV турнира"""
    text = (
        "➕ <b>Создать новый PPV турнир</b>\n\n"
        "Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="🌐 Загрузить из UFC API", callback_data="admin_create_from_api")],
        [InlineKeyboardButton(text="📝 Создать вручную", callback_data="admin_create_manual")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_status")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "admin_create_draft")
async def process_create_draft(callback: CallbackQuery):
    """Создание черновика турнира в БД из данных temp_event_data"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.answer("📝 Создаю черновик...")
    
    try:
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
        from db_utils import create_event_from_api, get_session
        
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


# ============ ОТКРЫТИЕ ДЛЯ СТАВОК ============

@router.callback_query(lambda c: c.data.startswith("admin_open_betting:"))
async def process_admin_open_betting(callback: CallbackQuery):
    """Открытие турнира для ставок"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer("🔄 Открываю для ставок...")
        
        from db_utils import get_session, open_event_for_bets, get_event_by_id
        
        async with get_session() as session:
            success = await open_event_for_bets(session, event_id)
            
            if success:
                event = await get_event_by_id(session, event_id)
                
                await callback.message.edit_text(
                    f"✅ <b>Турнир открыт для ставок!</b>\n\n"
                    f"🏆 <b>{event.title}</b>\n"
                    f"📊 Статус: <b>open_for_bets</b>\n\n"
                    f"Пользователи могут делать ставки!",
                    reply_markup=get_admin_menu(),
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    "❌ Не удалось открыть турнир для ставок",
                    reply_markup=get_admin_menu()
                )
                
    except Exception as e:
        logger.error(f"Ошибка open_betting: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ============ ЗАКРЫТИЕ ТУРНИРА ============

@router.callback_query(lambda c: c.data == "admin_close_event")
async def process_admin_close_event(callback: CallbackQuery):
    """Закрытие турнира - автоматическое получение результатов из API"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.answer("🔄 Получаю результаты из UFC API...")
    
    try:
        from db_utils import get_session, get_open_event_with_fights
        from api.results import get_todays_ufc_event_results
        
        async with get_session() as session:
            event_data = await get_open_event_with_fights(session)
            
            if not event_data:
                await callback.message.edit_text(
                    "🏁 <b>Закрытие турнира</b>\n\n"
                    "Нет открытых турниров для закрытия.",
                    reply_markup=get_admin_menu(),
                    parse_mode="HTML"
                )
                return
            
            event = event_data['event']
            fights = event_data['fights']
            
            # Получаем результаты из API
            api_results = get_todays_ufc_event_results()
            
            if not api_results:
                # Если API не вернул результаты, показываем ошибку
                text = (
                    f"🏁 <b>Закрытие турнира</b>\n\n"
                    f"🏆 <b>{event.title}</b>\n"
                    f"📅 {event.date_utc.strftime('%d.%m.%Y')}\n"
                    f"🥊 Боев: {len(fights)}\n\n"
                    f"❌ <b>Не удалось получить результаты из UFC API!</b>\n\n"
                    f"Возможные причины:\n"
                    f"• Турнир ещё не завершён\n"
                    f"• Проблемы с доступом к API\n"
                    f"• Результаты ещё не опубликованы\n\n"
                    f"Попробуйте позже или введите результаты вручную."
                )
                
                buttons = [
                    [InlineKeyboardButton(text="📝 Ввести вручную", callback_data=f"admin_input_results:{event.id}")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_status")]
                ]
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
                return
            
            # Сопоставляем результаты с нашими боями
            text = (
                f"🏁 <b>Закрытие турнира</b>\n\n"
                f"🏆 <b>{event.title}</b>\n"
                f"📅 {event.date_utc.strftime('%d.%m.%Y')}\n"
                f"🥊 Боев: {len(fights)}\n\n"
                f"<b>📊 Результаты с UFC API:</b>\n\n"
            )
            
            # Создаем словарь для обновления результатов
            results_to_save = []
            matches_found = 0
            
            for fight in fights:
                # Ищем соответствующий результат
                result = next(
                    (r for r in api_results if 
                     (r['fighter1'] in fight.fighter1_name and r['fighter2'] in fight.fighter2_name) or
                     (r['fighter1'] in fight.fighter2_name and r['fighter2'] in fight.fighter1_name)),
                    None
                )
                
                if result:
                    matches_found += 1
                    
                    # Определяем победителя (1 или 2)
                    if result['winner'] == 'draw':
                        winner_display = "🤝 Ничья"
                        winner_value = 'draw'
                    elif result['winner'] == 'nc':
                        winner_display = "❌ Не состоялся"
                        winner_value = 'nc'
                    else:
                        # Проверяем, какой боец победил
                        if result['winner'] == fight.fighter1_name or result['winner'] in fight.fighter1_name:
                            winner_display = f"✅ {fight.fighter1_name}"
                            winner_value = '1'
                        elif result['winner'] == fight.fighter2_name or result['winner'] in fight.fighter2_name:
                            winner_display = f"✅ {fight.fighter2_name}"
                            winner_value = '2'
                        else:
                            winner_display = f"✅ {result['winner']}"
                            winner_value = result['winner']
                    
                    # Сохраняем для последующего обновления
                    results_to_save.append({
                        'fight_id': fight.id,
                        'winner': winner_value
                    })
                    
                    text += f"<b>Бой {fight.fight_order}:</b> {fight.fighter1_name} vs {fight.fighter2_name}\n"
                    text += f"   → {winner_display}\n"
                else:
                    text += f"<b>Бой {fight.fight_order}:</b> {fight.fighter1_name} vs {fight.fighter2_name}\n"
                    text += f"   → ⚠️ <i>Результат не найден</i>\n"
            
            text += f"\n<b>Найдено результатов:</b> {matches_found}/{len(fights)}\n\n"
            
            if matches_found == len(fights):
                # Сохраняем результаты во временное хранилище
                from utils.states import temp_event_data
                user_id = callback.from_user.id
                if 'closing_results' not in temp_event_data:
                    temp_event_data['closing_results'] = {}
                temp_event_data['closing_results'][user_id] = {
                    'event_id': event.id,
                    'results': results_to_save
                }
                
                text += "<b>Все результаты получены. Закрыть турнир?</b>"
                buttons = [
                    [InlineKeyboardButton(text="✅ Да, закрыть", callback_data=f"admin_execute_close:{event.id}")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_status")]
                ]
            else:
                text += (
                    f"⚠️ <b>Не все результаты найдены!</b>\n"
                    f"Можно:\n"
                    f"• Попробовать снова позже\n"
                    f"• Ввести оставшиеся вручную"
                )
                buttons = [
                    [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="admin_close_event")],
                    [InlineKeyboardButton(text="📝 Ввести вручную", callback_data=f"admin_input_results:{event.id}")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_status")]
                ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка close_event: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_admin_menu()
        )

@router.callback_query(lambda c: c.data.startswith("admin_force_close:"))
async def process_admin_force_close(callback: CallbackQuery):
    """Принудительное закрытие турнира (пропуская бои без результатов)"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer("🔄 Закрываю турнир...")
        
        from db_utils import get_session, get_event_by_id, get_fights_for_event
        from db_utils import calculate_points_for_event
        
        async with get_session() as session:
            event = await get_event_by_id(session, event_id)
            fights = await get_fights_for_event(session, event_id)
            
            # Считаем только бои с результатами
            fights_with_results = [f for f in fights if f.winner]
            
            if not fights_with_results:
                await callback.message.edit_text(
                    "❌ Нет ни одного боя с результатом!",
                    reply_markup=get_admin_menu()
                )
                return
            
            # Рассчитываем очки только по боям с результатами
            points_result = await calculate_points_for_event(session, event_id)
            
            if not points_result:
                await callback.message.edit_text(
                    "❌ Ошибка при расчёте очков",
                    reply_markup=get_admin_menu()
                )
                return
            
            event.status = 'finished'
            await session.commit()
            
            report = (
                f"✅ <b>Турнир принудительно закрыт!</b>\n\n"
                f"🏆 <b>{event.title}</b>\n"
                f"📊 <b>Статистика:</b>\n"
                f"• Всего боёв: {len(fights)}\n"
                f"• Боев с результатами: {len(fights_with_results)}\n"
                f"• Боев без результатов: {len(fights) - len(fights_with_results)}\n"
                f"• Обработано ставок: {points_result.get('total_bets', 0)}\n"
                f"• Обновлено игроков: {points_result.get('updated', 0)}\n\n"
                f"⚠️ <i>Бои без результатов не учитывались в расчёте!</i>\n\n"
                f"🏁 Турнир перемещён в архив."
            )
            
            await callback.message.edit_text(
                report,
                reply_markup=get_admin_menu(),
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Ошибка force_close: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_admin_menu()
        )

@router.callback_query(lambda c: c.data.startswith("admin_execute_close:"))
async def process_admin_execute_close(callback: CallbackQuery):
    """Финальное закрытие турнира с автоматическим расчётом"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    try:
        event_id = int(callback.data.split(":")[1])
        await callback.answer("🔄 Закрываю турнир и рассчитываю очки...")
        
        from db_utils import get_session, get_event_by_id, get_fights_for_event
        from db_utils import calculate_points_for_event
        from database import Event, Fight
        
        async with get_session() as session:
            # 1. Получаем турнир
            event = await get_event_by_id(session, event_id)
            if not event:
                await callback.message.edit_text(
                    "❌ Турнир не найден",
                    reply_markup=get_admin_menu()
                )
                return
            
            # 2. Проверяем, есть ли сохранённые результаты из API
            from utils.states import temp_event_data
            user_id = callback.from_user.id
            saved_results = temp_event_data.get('closing_results', {}).get(user_id)
            
            if saved_results and saved_results['event_id'] == event_id:
                # Обновляем результаты из API
                for result in saved_results['results']:
                    fight = await session.get(Fight, result['fight_id'])
                    if fight:
                        fight.winner = result['winner']
                await session.commit()
                logger.info(f"Обновлены результаты для {len(saved_results['results'])} боёв из API")
                
                # Очищаем временные данные
                del temp_event_data['closing_results'][user_id]
            
            # 3. Проверяем, что все результаты введены
            fights = await get_fights_for_event(session, event_id)
            missing_results = [f for f in fights if not f.winner]
            
            if missing_results:
                # Показываем, каких результатов не хватает
                text = f"❌ Не введены результаты для {len(missing_results)} боёв:\n"
                for fight in missing_results[:5]:
                    text += f"• Бой {fight.fight_order}: {fight.fighter1_name} vs {fight.fighter2_name}\n"
                if len(missing_results) > 5:
                    text += f"• ... и ещё {len(missing_results) - 5}\n"
                
                await callback.message.edit_text(
                    text + "\nСначала введите результаты.",
                    reply_markup=get_admin_menu()
                )
                return
            
            # 4. Рассчитываем очки для всех игроков
            points_result = await calculate_points_for_event(session, event_id)
            
            if not points_result:
                await callback.message.edit_text(
                    "❌ Ошибка при расчёте очков",
                    reply_markup=get_admin_menu()
                )
                return
            
            # 5. Меняем статус турнира
            event.status = 'finished'
            await session.commit()
            
            # 6. Формируем отчёт
            report = (
                f"✅ <b>Турнир успешно закрыт!</b>\n\n"
                f"🏆 <b>{event.title}</b>\n"
                f"📊 <b>Статистика:</b>\n"
                f"• Всего боёв: {len(fights)}\n"
                f"• Обработано ставок: {points_result.get('total_bets', 0)}\n"
                f"• Обновлено игроков: {points_result.get('updated', 0)}\n\n"
                f"🏁 Турнир перемещён в архив."
            )
            
            await callback.message.edit_text(
                report,
                reply_markup=get_admin_menu(),
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Ошибка execute_close: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)[:100]}",
            reply_markup=get_admin_menu()
        )

# ============ ОБНОВЛЕНИЕ ОДНОГО БОЯ ============

@router.callback_query(lambda c: c.data.startswith("admin_update_single:"))
async def process_admin_update_single(callback: CallbackQuery):
    """Обновление результата одного боя"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    try:
        parts = callback.data.split(":")
        event_id = int(parts[1])
        fight_id = int(parts[2])
        
        await callback.answer()
        
        from db_utils import get_session
        from database import Fight
        from sqlalchemy import select
        
        async with get_session() as session:
            fight = await session.get(Fight, fight_id)
            
            if not fight:
                await callback.answer("❌ Бой не найден", show_alert=True)
                return
            
            text = (
                f"📝 <b>Обновление результата боя</b>\n\n"
                f"<b>Бой {fight.fight_order}:</b>\n"
                f"{fight.fighter1_name} vs {fight.fighter2_name}\n\n"
                f"<b>Выберите победителя:</b>"
            )
            
            buttons = [
                [InlineKeyboardButton(text=f"👊 {fight.fighter1_name}", callback_data=f"admin_set_winner:{event_id}:{fight_id}:1")],
                [InlineKeyboardButton(text=f"🥊 {fight.fighter2_name}", callback_data=f"admin_set_winner:{event_id}:{fight_id}:2")],
                [InlineKeyboardButton(text="🤝 Ничья", callback_data=f"admin_set_winner:{event_id}:{fight_id}:draw")],
                [InlineKeyboardButton(text="❌ Отменён", callback_data=f"admin_set_winner:{event_id}:{fight_id}:cancelled")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_input_results:{event_id}")]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Ошибка update_single: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ============ СТАТУС СИСТЕМЫ ============

async def show_system_status(callback: CallbackQuery):
    """Показ статуса системы"""
    try:
        from db_utils import get_session
        from database import User, Event, Bet
        from sqlalchemy import select, func
        
        async with get_session() as session:
            # Статистика
            users_count = await session.scalar(select(func.count(User.user_id)))
            events_count = await session.scalar(select(func.count(Event.id)))
            bets_count = await session.scalar(select(func.count(Bet.id)))
            
            # Текущий турнир
            current_event = await session.scalar(
                select(Event).where(Event.status == 'open_for_bets').limit(1)
            )
            
            # Черновики
            draft_events = await session.scalars(
                select(Event).where(Event.status == 'draft')
            )
            draft_count = len(list(draft_events.all()))
            
            text = (
                "ℹ️ <b>Статус системы</b>\n\n"
                f"👥 Пользователей: {users_count}\n"
                f"🏆 Турниров: {events_count}\n"
                f"🎯 Ставок: {bets_count}\n"
                f"📝 Черновиков: {draft_count}\n\n"
            )
            
            if current_event:
                text += f"📊 <b>Активный турнир:</b>\n{current_event.title}\n"
            else:
                text += "📊 Активных турниров нет\n"
            
            try:
                await callback.message.edit_text(
                    text,
                    reply_markup=get_admin_menu(),
                    parse_mode="HTML"
                )
            except Exception as edit_error:
                # Если сообщение не изменилось - просто отвечаем
                if "message is not modified" in str(edit_error):
                    await callback.answer("✅ Статус обновлён")
                else:
                    raise
            
    except Exception as e:
        logger.error(f"Ошибка show_system_status: {e}", exc_info=True)
        try:
            await callback.message.edit_text(
                "❌ Ошибка загрузки статуса",
                reply_markup=get_admin_menu()
            )
        except:
            await callback.answer("❌ Ошибка", show_alert=True)
