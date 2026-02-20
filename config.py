import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env (создадим позже)
load_dotenv()

# Токен бота из переменной окружения BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID администратора (ваш Telegram user_id)
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Режим разработки (True = использовать тестовые данные, False = использовать реальный API)
DEBUG_MODE = False  # Поставьте False, когда будете готовы к реальным данным

# Настройки базы данных
DB_NAME = "ufc_bot_test.db" if DEBUG_MODE else "ufc_bot.db"

# API UFC
UFC_API_URL = "http://ufc-data-api.ufc.com/api/v3/us/events"

# Проверка обязательных переменных
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен! Создайте файл .env")