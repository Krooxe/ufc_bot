import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Float, BigInteger, DateTime, ForeignKey, Text, DECIMAL, Index
from datetime import datetime
import config

# Создаем движок для асинхронной работы с SQLite
engine = create_async_engine(
    f"sqlite+aiosqlite:///{config.DB_NAME}",
    echo=False,  # Поставьте True, чтобы видеть SQL-запросы в консоли (для отладки)
)

# Фабрика сессий
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Базовый класс для моделей
Base = declarative_base()

# ==================== МОДЕЛИ БАЗЫ ДАННЫХ ====================

class User(Base):
    """Таблица пользователей"""
    __tablename__ = "users"
    
    user_id = Column(BigInteger, primary_key=True)  # Telegram User ID
    username = Column(String(100))
    full_name = Column(String(200))
    total_balance = Column(DECIMAL(10, 2), default=0.0)
    created_at = Column(DateTime, default=datetime.now)

class Event(Base):
    """Таблица турниров"""
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True)
    ufc_api_id = Column(Integer, unique=True)
    title = Column(String(300), nullable=False)
    short_title = Column(String(100), nullable=False)
    year = Column(Integer, nullable=False)
    date_utc = Column(DateTime, nullable=False)
    date_msk = Column(DateTime, nullable=False)
    status = Column(String(50), default="draft")  # draft, open_for_bets, finished
    created_at = Column(DateTime, default=datetime.now)

class Fight(Base):
    """Таблица боев"""
    __tablename__ = "fights"
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    fight_order = Column(Integer)
    fighter1_name = Column(String(200), nullable=False)
    fighter2_name = Column(String(200), nullable=False)
    odds1 = Column(DECIMAL(10, 2))
    odds2 = Column(DECIMAL(10, 2))
    winner = Column(String(20))  # '1', '2', 'draw', 'nc'

class Bet(Base):
    """Таблица ставок"""
    __tablename__ = "bets"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    fight_id = Column(Integer, ForeignKey("fights.id"), nullable=False)
    bet_type = Column(String(20), nullable=False)  # 'main', 'insurance'
    chosen_fighter = Column(Integer, nullable=False)  # 1 или 2
    odds_at_bet = Column(DECIMAL(10, 2), nullable=False)
    status = Column(String(20), default="pending")  # pending, win, lose, cancelled
    points_earned = Column(DECIMAL(10, 2), default=0)
    placed_at = Column(DateTime, default=datetime.now)

class Setting(Base):
    """Таблица настроек"""
    __tablename__ = "settings"
    
    key = Column(String(100), primary_key=True)
    value = Column(Text)

class FightResult(Base):
    """Таблица для хранения результатов боев из API (архив)"""
    __tablename__ = "fight_results"
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"))
    fight_order = Column(Integer)
    fighter1_name = Column(String(200), nullable=False)
    fighter2_name = Column(String(200), nullable=False)
    odds1 = Column(DECIMAL(10, 2))
    odds2 = Column(DECIMAL(10, 2))
    winner = Column(String(20))  # '1', '2', 'draw', 'nc', 'cancelled'
    method = Column(String(100))  # KO, submission, decision и т.д.
    round_ended = Column(Integer)
    time_ended = Column(String(20))
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Индекс для быстрого поиска
    __table_args__ = (
        Index('idx_event_fight', 'event_id', 'fight_order'),
    )
    
# ==================== УТИЛИТЫ ====================

async def create_tables():
    """Создание всех таблиц в базе данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Таблицы в базе данных созданы")

async def get_session() -> AsyncSession:
    """Получение асинхронной сессии для работы с БД"""
    async with async_session() as session:
        yield session

# ==================== ТЕСТОВЫЙ ЗАПУСК ====================

async def test_database():
    """Тестовая функция для проверки работы БД"""
    await create_tables()
    
    # Проверяем, что файл БД создался
    import os
    if os.path.exists(config.DB_NAME):
        print(f"✅ Файл базы данных '{config.DB_NAME}' создан")
    else:
        print(f"❌ Файл базы данных не создан")

if __name__ == "__main__":
    # Запускаем тест
    asyncio.run(test_database())