# test.py - СИСТЕМА ТЕСТИРОВАНИЯ (УСКОРЕНИЕ ВРЕМЕНИ)

import logging
from datetime import datetime, timedelta
from typing import Optional

from config import TEST_MODE, TIME_MULTIPLIER, ADMIN_IDS

logger = logging.getLogger(__name__)

# ============================================================
# 1. ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================================

_test_mode_active = False
_test_start_time = None


# ============================================================
# 2. УПРАВЛЕНИЕ ТЕСТ-РЕЖИМОМ
# ============================================================

def is_test_mode() -> bool:
    """Возвращает True, если тестовый режим включён"""
    global _test_mode_active
    return _test_mode_active


def enable_test_mode():
    """Включает тестовый режим"""
    global _test_mode_active, _test_start_time
    _test_mode_active = True
    _test_start_time = datetime.now()
    logger.info("⏱️ ТЕСТОВЫЙ РЕЖИМ ВКЛЮЧЁН (1 час = 1 секунда)")


def disable_test_mode():
    """Выключает тестовый режим"""
    global _test_mode_active, _test_start_time
    _test_mode_active = False
    _test_start_time = None
    logger.info("⏱️ ТЕСТОВЫЙ РЕЖИМ ВЫКЛЮЧЕН")


def get_test_status() -> dict:
    """Возвращает статус тестового режима"""
    global _test_mode_active, _test_start_time
    return {
        'active': _test_mode_active,
        'started_at': _test_start_time,
        'multiplier': TIME_MULTIPLIER if _test_mode_active else 1
    }


# ============================================================
# 3. КОРРЕКТИРОВКА ВРЕМЕНИ
# ============================================================

def get_adjusted_time(real_time: datetime) -> datetime:
    """
    Преобразует реальное время в "ускоренное" для тестового режима.
    В тестовом режиме 1 час = 1 секунда.
    """
    if not _test_mode_active:
        return real_time
    
    # В тестовом режиме время идёт в 3600 раз быстрее
    # Но для простоты мы не сдвигаем время, а просто возвращаем реальное
    # Все интервалы делим на 3600 при расчётах
    return real_time


def get_adjusted_seconds(real_seconds: int) -> int:
    """
    Преобразует реальные секунды в "ускоренные" для тестового режима.
    1 час (3600 сек) → 1 секунда
    """
    if not _test_mode_active:
        return real_seconds
    
    # Делим на 3600, но минимум 1 секунда
    return max(1, real_seconds // TIME_MULTIPLIER)


def get_adjusted_hours(real_hours: int) -> int:
    """
    Преобразует реальные часы в "ускоренные" для тестового режима.
    1 час → 1 секунда (возвращаем секунды)
    """
    if not _test_mode_active:
        return real_hours
    
    # 1 час = 1 секунда
    return max(1, real_hours // 3600)


def get_time_since(last_time: datetime) -> float:
    """
    Возвращает количество "ускоренных" секунд с момента last_time.
    В тестовом режиме время ускорено в 3600 раз.
    """
    if not _test_mode_active:
        return (datetime.now() - last_time).total_seconds()
    
    # В тестовом режиме: реальные секунды / 3600
    real_seconds = (datetime.now() - last_time).total_seconds()
    return max(0, real_seconds / TIME_MULTIPLIER)


def get_time_since_hours(last_time: datetime) -> float:
    """
    Возвращает количество "ускоренных" часов с момента last_time.
    В тестовом режиме 1 реальный час = 1 секунда (0.00027 часов)
    """
    if not _test_mode_active:
        return (datetime.now() - last_time).total_seconds() / 3600
    
    # В тестовом режиме считаем в секундах (1 час = 1 секунда)
    real_seconds = (datetime.now() - last_time).total_seconds()
    return max(0, real_seconds / TIME_MULTIPLIER)


# ============================================================
# 4. КОМАНДА ДЛЯ БОТА
# ============================================================

async def cmd_test(message):
    """/test on — включить тестовый режим (1 час = 1 сек)
       /test off — выключить тестовый режим
       /test status — статус тестового режима"""
    
    from config import is_admin
    if not is_admin(message.from_user.id):
        await message.answer("❌ Ты не админ!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        return await message.answer(
            "📝 *Тестовый режим*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/test on — включить ускорение (1 час = 1 сек)\n"
            "/test off — выключить ускорение\n"
            "/test status — статус\n\n"
            f"📊 Текущий статус: {'🟢 ВКЛЮЧЁН' if is_test_mode() else '🔴 ВЫКЛЮЧЕН'}",
            parse_mode='Markdown'
        )
    
    action = args[1].lower()
    
    if action == 'on':
        enable_test_mode()
        await message.answer(
            "⏱️ *Режим тестирования ВКЛЮЧЁН!*\n\n"
            "🔄 1 час = 1 секунда\n"
            "🔄 24 часа = 24 секунды\n"
            "🔄 7 дней = 168 секунд\n\n"
            "⚠️ Все временные интервалы ускорены в 3600 раз!\n"
            "💡 Используй `/test off` чтобы выключить.",
            parse_mode='Markdown'
        )
    elif action == 'off':
        disable_test_mode()
        await message.answer(
            "⏱️ *Режим тестирования ВЫКЛЮЧЕН!*\n\n"
            "🔄 Время вернулось в нормальный режим.",
            parse_mode='Markdown'
        )
    elif action == 'status':
        status = get_test_status()
        await message.answer(
            f"📊 *Статус тестового режима*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Состояние: {'🟢 ВКЛЮЧЁН' if status['active'] else '🔴 ВЫКЛЮЧЕН'}\n"
            f"Множитель: x{status['multiplier']}\n"
            f"Включён: {status['started_at'].strftime('%d.%m.%Y %H:%M:%S') if status['started_at'] else '—'}",
            parse_mode='Markdown'
        )
    else:
        await message.answer("❌ Используй: `/test on`, `/test off` или `/test status`", parse_mode='Markdown')
