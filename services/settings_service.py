"""
Settings Service - настройки приложения
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import Setting

logger = logging.getLogger(__name__)


async def get_setting(session: AsyncSession, key: str) -> Optional[str]:
    """Получает значение настройки"""
    try:
        result = await session.execute(
            select(Setting.value).where(Setting.key == key)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Ошибка получения настройки {key}: {e}")
        return None


async def set_setting(session: AsyncSession, key: str, value: str) -> bool:
    """Устанавливает значение настройки"""
    try:
        result = await session.execute(
            select(Setting).where(Setting.key == key)
        )
        setting = result.scalar_one_or_none()
        
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            session.add(setting)
        
        await session.commit()
        logger.info(f"Настройка {key} установлена в {value}")
        return True
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка установки настройки {key}: {e}")
        return False


async def delete_setting(session: AsyncSession, key: str) -> bool:
    """Удаляет настройку"""
    try:
        result = await session.execute(
            select(Setting).where(Setting.key == key)
        )
        setting = result.scalar_one_or_none()
        
        if setting:
            await session.delete(setting)
            await session.commit()
            logger.info(f"Настройка {key} удалена")
            return True
        return False
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка удаления настройки {key}: {e}")
        return False


async def get_all_settings(session: AsyncSession) -> dict:
    """Получает все настройки в виде словаря"""
    try:
        result = await session.execute(
            select(Setting).order_by(Setting.key)
        )
        settings = result.scalars().all()
        return {s.key: s.value for s in settings}
    except Exception as e:
        logger.error(f"Ошибка получения всех настроек: {e}")
        return {}