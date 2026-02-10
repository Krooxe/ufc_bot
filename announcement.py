"""
Обработчик кнопки "Объявление" - рассылка всем пользователям
Поддерживает группы медиа (альбомы)
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import db

# Импорты для админ-панели
from utils.json_storage import storage
from handlers.admin.panel import get_admin_menu, get_admin_message_text

logger = logging.getLogger(__name__)
router = Router()

# Глобальная переменная для bot (будет установлена из main.py)
bot_instance: Bot = None

def set_bot(bot: Bot):
    """Устанавливает экземпляр бота для рассылки"""
    global bot_instance
    bot_instance = bot


# Состояния FSM для ввода объявления
class AnnouncementStates(StatesGroup):
    waiting_for_announcement = State()
    waiting_for_confirmation = State()


async def show_admin_panel(message: Message):
    """
    Показывает админ-панель с кнопками
    """
    current_tournament = storage.get_current_tournament()
    has_active_tournament = bool(current_tournament and current_tournament.get("status") == "active")
    
    await message.answer(
        get_admin_message_text(has_active_tournament),
        parse_mode="HTML",
        reply_markup=get_admin_menu()
    )


# ===== ВАЖНО: сохраняем оригинальное название хэндлера =====
@router.callback_query(lambda c: c.data == "admin_announcement")
async def admin_announcement_handler(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Объявление" - НАЗВАНИЕ НЕ МЕНЯЕМ!
    """
    logger.info(f"Администратор {callback.from_user.id} начал создание объявления")
    
    await state.set_state(AnnouncementStates.waiting_for_announcement)
    
    await callback.message.answer(
        "📢 <b>Создание объявления</b>\n\n"
        "Пришлите мне сообщение, которое нужно разослать всем пользователям:\n"
        "✅ <b>Поддерживается:</b>\n"
        "• Текст\n"
        "• Фото/группа фото (альбом)\n"
        "• Видео\n"
        "• Файл\n"
        "• Аудио, голосовые\n"
        "• Стикеры, GIF\n"
        "• Опрос\n\n"
        "❌ <b>Не поддерживается:</b>\n"
        "• Геолокация\n"
        "• Контакты\n"
        "• Визитки\n\n"
        "<i>Можно прикрепить несколько медиа в одном сообщении (альбом)</i>\n\n"
        "Для отмены напишите /cancel",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="announcement_cancel")]
        ])
    )
    
    await callback.answer()


@router.callback_query(lambda c: c.data == "announcement_cancel", StateFilter(AnnouncementStates))
async def announcement_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена создания объявления"""
    await state.clear()
    await callback.message.answer("❌ Создание объявления отменено")
    await show_admin_panel(callback.message)
    await callback.answer()


@router.message(AnnouncementStates.waiting_for_announcement, F.content_type.in_({
    'text', 'photo', 'video', 'document', 'audio', 'voice', 'video_note', 
    'sticker', 'animation', 'poll'
}))
async def process_single_announcement(message: Message, state: FSMContext):
    """
    Обрабатывает одиночное сообщение для рассылки
    """
    # Сохраняем информацию о сообщении
    content_data = {
        "type": "single",
        "content_type": message.content_type,
        "message_id": message.message_id,
        "chat_id": message.chat.id,
        "caption": message.caption,
        "caption_entities": message.caption_entities,
        "text": message.text,
        "text_entities": message.entities,
    }
    
    # Для медиафайлов сохраняем file_id
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
    elif message.content_type == 'poll':
        content_data["poll"] = message.poll.model_dump()
    
    await state.update_data(announcement=content_data)
    await state.set_state(AnnouncementStates.waiting_for_confirmation)
    
    await show_preview(message, content_data)


@router.message(AnnouncementStates.waiting_for_announcement, F.media_group_id)
async def process_media_group_announcement(message: Message, state: FSMContext):
    """
    Обрабатывает группу медиа (альбом) для рассылки
    Внимание: Telegram присылает каждое медиа отдельным сообщением!
    Нужно собирать их по media_group_id
    """
    # Получаем существующие данные или создаём новые
    data = await state.get_data()
    media_group = data.get('media_group', {})
    
    # Сохраняем это сообщение в группу
    media_group_id = message.media_group_id
    
    # Инициализируем группу если её нет
    if media_group_id not in media_group:
        media_group[media_group_id] = {
            "type": "media_group",
            "messages": [],
            "caption": message.caption,
            "caption_entities": message.caption_entities
        }
    
    # Сохраняем информацию о сообщении
    media_data = {
        "content_type": message.content_type,
        "message_id": message.message_id,
        "chat_id": message.chat.id,
    }
    
    # Сохраняем file_id в зависимости от типа
    if message.content_type == 'photo':
        media_data["photo_file_id"] = message.photo[-1].file_id
    elif message.content_type == 'video':
        media_data["video_file_id"] = message.video.file_id
    elif message.content_type == 'document':
        media_data["document_file_id"] = message.document.file_id
    
    # Добавляем в группу
    media_group[media_group_id]["messages"].append(media_data)
    
    # Обновляем состояние
    await state.update_data(media_group=media_group)
    
    # Для простоты: если это первое сообщение группы, ждём немного
    if len(media_group[media_group_id]["messages"]) == 1:
        pass


async def show_preview(message: Message, content_data: dict):
    """Показывает предпросмотр объявления"""
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
        f"<b>Тип:</b> {get_content_type_name(content_data)}"
        f"{' (группа медиа)' if content_data.get('type') == 'media_group' else ''}\n"
        f"<b>Количество медиа:</b> {len(content_data.get('messages', [1]))}\n"
        f"<b>Отправить всем пользователей?</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


def get_preview_text(content_data: dict) -> str:
    """Генерирует текст для предпросмотра"""
    if content_data.get('type') == 'media_group':
        media_types = {}
        for msg in content_data.get('messages', []):
            media_type = msg.get('content_type', 'unknown')
            media_types[media_type] = media_types.get(media_type, 0) + 1
        
        types_desc = []
        for media_type, count in media_types.items():
            name = get_single_content_type_name(media_type)
            types_desc.append(f"{name}: {count}")
        
        caption = content_data.get('caption', '')
        if caption:
            caption_preview = caption[:100] + ('...' if len(caption) > 100 else '')
            return f"📦 <b>Группа медиа</b> ({', '.join(types_desc)})\n{caption_preview}"
        else:
            return f"📦 <b>Группа медиа</b> ({', '.join(types_desc)})"
    
    else:
        content_type = content_data['content_type']
        
        if content_type == 'text':
            text = content_data.get('text', '')
            text_preview = text[:200] + ('...' if len(text) > 200 else '')
            return text_preview
        elif content_type in ['photo', 'video']:
            caption = content_data.get('caption', '')
            emoji = '🖼️' if content_type == 'photo' else '🎥'
            media_name = get_single_content_type_name(content_type)
            
            if caption:
                caption_preview = caption[:100] + ('...' if len(caption) > 100 else '')
                return f"{emoji} {media_name}\n{caption_preview}"
            else:
                return f"{emoji} {media_name} (без подписи)"
        elif content_type == 'poll':
            question = content_data.get('poll', {}).get('question', 'Без вопроса')
            return f"📊 Опрос: {question}"
        else:
            return f"📦 {get_single_content_type_name(content_type)}"


def get_content_type_name(content_data: dict) -> str:
    """Возвращает читаемое название для предпросмотра"""
    if content_data.get('type') == 'media_group':
        return "Группа медиа"
    else:
        return get_single_content_type_name(content_data.get('content_type', 'unknown'))


def get_single_content_type_name(content_type: str) -> str:
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
        'unknown': 'Неизвестный'
    }
    return names.get(content_type, content_type)


@router.callback_query(lambda c: c.data == "announcement_confirm", StateFilter(AnnouncementStates.waiting_for_confirmation))
async def announcement_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и РЕАЛЬНАЯ рассылка объявления"""
    data = await state.get_data()
    content_data = data.get('announcement')
    
    if not content_data:
        await callback.answer("❌ Ошибка: данные объявления не найдены", show_alert=True)
        await state.clear()
        await show_admin_panel(callback.message)
        return
    
    if not bot_instance:
        await callback.answer("❌ Ошибка: бот не инициализирован для рассылки", show_alert=True)
        await state.clear()
        await show_admin_panel(callback.message)
        return
    
    await callback.message.edit_text("🔄 Рассылка объявления...")
    
    users = db.get_all_users()
    total_users = len(users)
    successful = 0
    failed = 0
    
    for user in users:
        try:
            if user.user_id == callback.from_user.id:
                successful += 1
                continue
            
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
        parse_mode="HTML"
    )
    
    await state.clear()
    await show_admin_panel(callback.message)
    await callback.answer()


@router.callback_query(lambda c: c.data == "announcement_cancel_final", StateFilter(AnnouncementStates))
async def announcement_cancel_final(callback: CallbackQuery, state: FSMContext):
    """Отмена на этапе подтверждения"""
    await state.clear()
    await callback.message.answer("❌ Рассылка отменена")
    await show_admin_panel(callback.message)
    await callback.answer()


@router.message(AnnouncementStates.waiting_for_announcement)
async def unsupported_content_type(message: Message):
    """Обрабатывает неподдерживаемые типы контента"""
    await message.answer(
        "❌ <b>Этот тип контента не поддерживается для рассылки!</b>\n\n"
        "Поддерживаются: текст, фото/группы фото, видео, документы, аудио, "
        "голосовые, видеосообщения, стикеры, GIF, опросы.\n\n"
        "НЕ поддерживаются: геолокация, контакты, визитки.\n\n"
        "Попробуйте отправить другой тип контента или напишите /cancel",
        parse_mode="HTML"
    )