import logging
from datetime import datetime
from typing import Optional

from config import ADMIN_IDS

logger = logging.getLogger(__name__)

_test_mode_active = False
_test_start_time = None
TIME_MULTIPLIER = 3600


def is_test_mode() -> bool:
    global _test_mode_active
    return _test_mode_active


def enable_test_mode():
    global _test_mode_active, _test_start_time
    _test_mode_active = True
    _test_start_time = datetime.now()
    logger.info("⏱️ ТЕСТОВЫЙ РЕЖИМ ВКЛЮЧЁН (1 час = 1 секунда)")


def disable_test_mode():
    global _test_mode_active, _test_start_time
    _test_mode_active = False
    _test_start_time = None
    logger.info("⏱️ ТЕСТОВЫЙ РЕЖИМ ВЫКЛЮЧЕН")


def get_test_status() -> dict:
    global _test_mode_active, _test_start_time
    return {
        'active': _test_mode_active,
        'started_at': _test_start_time,
        'multiplier': TIME_MULTIPLIER if _test_mode_active else 1
    }


def get_adjusted_seconds(real_seconds: int) -> int:
    if not _test_mode_active:
        return real_seconds
    return max(1, real_seconds // TIME_MULTIPLIER)


def get_time_since_hours(last_time: datetime) -> float:
    real_seconds = (datetime.now() - last_time).total_seconds()
    if not _test_mode_active:
        return real_seconds / 3600
    return real_seconds / TIME_MULTIPLIER


def get_time_since(last_time: datetime) -> float:
    real_seconds = (datetime.now() - last_time).total_seconds()
    if not _test_mode_active:
        return real_seconds
    return real_seconds / TIME_MULTIPLIER


async def cmd_test(message):
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
