"""
Обработчики объявлений и рассылок
Создание, подтверждение и отправка объявлений всем пользователям
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import config
from utils.keyboards import get_admin_menu
from utils.states import AdminStates
from db_utils import get_session, get_all_users

logger = logging.getLogger(__name__)

# Создаём роутер для объявлений
router = Router()

# Глобальная переменная для bot (будет установлена из main)
bot_instance: Bot = None


def set_bot(bot: Bot):
    """Устанавливает экземпляр бота для рассылки"""
    global bot_instance
    bot_instance = bot


@router.callback_query(lambda c: c.data == "admin_announce")
async def process_admin_announce(callback: CallbackQuery, state: FSMContext):
    """Начало создания объявления"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_announcement)
    
    text = (
        "📢 <b>Создание объявления</b>\n\n"
        "Пришлите мне сообщение, которое нужно разослать всем пользователям:\n"
        "✅ <b>Поддерживается:</b>\n"
        "• Текст\n• Фото/группа фото (альбом)\n• Видео\n• Документы\n"
        "• Аудио, голосовые\n• Стикеры, GIF\n• Опрос\n\n"
        "❌ <b>Не поддерживается:</b>\n"
        "• Геолокация\n• Контакты\n• Визитки\n\n"
        "<i>Можно прикрепить несколько медиа в одном сообщении (альбом)</i>\n\n"
        "Для отмены напишите /cancel или нажмите кнопку 'Назад'"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
        ]),
        parse_mode="HTML"
    )


@router.message(AdminStates.waiting_for_announcement, F.content_type.in_({
    'text', 'photo', 'video', 'document', 'audio', 'voice', 'video_note', 
    'sticker', 'animation', 'poll'
}))
async def process_single_announcement(message: Message, state: FSMContext):
    """Обрабатывает одиночное сообщение для рассылки"""
    # Сохраняем данные сообщения
    content_data = {
        "type": "single",
        "content_type": message.content_type,
        "message_id": message.message_id,
        "chat_id": message.chat.id,
        "caption": message.caption,
        "text": message.text,
    }
    
    # Сохраняем file_id для медиа
    if message.content_type == 'photo':
        content_data["photo_file_id"] = message.photo[-1].file_id
    elif message.content_type == 'video':
        content_data["video_file_id"] = message.video.file_id
    elif message.content_type == 'document':
        content_data["document_file_id"] = message.document.file_id
    elif message.content_type == 'audio':
        content_data["audio_file_id"] = message.audio.file_id
    elif message.content_type == 'voice':
        content_data["voice_file_id"] = message.voice.file_id
    elif message.content_type == 'video_note':
        content_data["video_note_file_id"] = message.video_note.file_id
    elif message.content_type == 'sticker':
        content_data["sticker_file_id"] = message.sticker.file_id
    elif message.content_type == 'animation':
        content_data["animation_file_id"] = message.animation.file_id
    
    await state.update_data(announcement=content_data)
    
    # Показываем предпросмотр
    preview_text = get_preview_text(content_data)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Разослать всем", callback_data="announcement_confirm"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="announcement_cancel_final")
        ]
    ])
    
    await message.answer(
        f"📋 <b>Предпросмотр объявления:</b>\n\n"
        f"{preview_text}\n\n"
        f"<b>Тип:</b> {get_content_type_name(content_data)}\n"
        f"<b>Отправить всем пользователям?</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


def get_preview_text(content_data: dict) -> str:
    """Генерирует текст для предпросмотра"""
    content_type = content_data['content_type']
    
    if content_type == 'text':
        text = content_data.get('text', '')
        text_preview = text[:200] + ('...' if len(text) > 200 else '')
        return text_preview
    elif content_type in ['photo', 'video']:
        caption = content_data.get('caption', '')
        media_name = "Фото" if content_type == 'photo' else "Видео"
        
        if caption:
            caption_preview = caption[:100] + ('...' if len(caption) > 100 else '')
            return f"{media_name}\n{caption_preview}"
        else:
            return f"{media_name} (без подписи)"
    elif content_type == 'poll':
        return f"📊 Опрос"
    else:
        names = {
            'document': 'Документ',
            'audio': 'Аудио',
            'voice': 'Голосовое',
            'sticker': 'Стикер',
            'animation': 'GIF',
        }
        return f"📦 {names.get(content_type, content_data['content_type'])}"


def get_content_type_name(content_data: dict) -> str:
    """Возвращает читаемое название типа контента"""
    names = {
        'text': 'Текст',
        'photo': 'Фото',
        'video': 'Видео',
        'document': 'Документ',
        'audio': 'Аудио',
        'voice': 'Голосовое',
        'video_note': 'Видеосообщение',
        'sticker': 'Стикер',
        'animation': 'GIF',
        'poll': 'Опрос',
    }
    return names.get(content_data.get('content_type', 'unknown'), 'Неизвестный')


@router.callback_query(lambda c: c.data == "announcement_confirm")
async def announcement_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и рассылка объявления"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    data = await state.get_data()
    content_data = data.get('announcement')
    
    if not content_data:
        await callback.answer("❌ Ошибка: данные объявления не найдены", show_alert=True)
        await state.clear()
        await callback.message.answer("❌ Ошибка рассылки", reply_markup=get_admin_menu())
        return
    
    await callback.message.edit_text("🔄 Рассылка объявления...")
    
    # Используем bot_instance для рассылки
    global bot_instance
    if not bot_instance:
        await callback.message.answer("❌ Ошибка: bot не инициализирован", reply_markup=get_admin_menu())
        await state.clear()
        return
    
    # Получаем всех пользователей
    async with get_session() as session:
        users = await get_all_users(session)
        total_users = len(users)
        successful = 0
        failed = 0
        
        for user in users:
            try:
                await bot_instance.copy_message(
                    chat_id=user.user_id,
                    from_chat_id=content_data['chat_id'],
                    message_id=content_data['message_id']
                )
                successful += 1
                
            except Exception as e:
                logger.error(f"Ошибка при отправке пользователю {user.user_id}: {e}")
                failed += 1
    
    status_text = ""
    if successful == 0:
        status_text = "❌ Никому не удалось отправить"
    elif failed == 0:
        status_text = f"✅ Отправлено всем {successful} пользователям"
    else:
        status_text = f"⚠️ Отправлено {successful}/{total_users}"
    
    await callback.message.answer(
        f"✅ <b>Рассылку объявления завершена!</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего пользователей: {total_users}\n"
        f"• Успешно отправлено: {successful} ✅\n"
        f"• Ошибок отправки: {failed} ❌\n"
        f"• Тип: {get_content_type_name(content_data)}\n\n"
        f"{status_text}",
        parse_mode="HTML",
        reply_markup=get_admin_menu()
    )
    
    await state.clear()


@router.callback_query(lambda c: c.data == "announcement_cancel_final")
async def announcement_cancel_final(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки на этапе подтверждения"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Рассылка отменена",
        reply_markup=get_admin_menu()
    )
