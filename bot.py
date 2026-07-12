# bot.py

import logging
import random
import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from config import (
    CHAT_ID, ADMIN_CHAT_ID, ADMIN_IDS, 
    is_admin, is_allowed_chat, get_rank_by_streak,
    TRIGGER_SYMBOLS, MOOD_SYMBOLS
)
from db import (
    get_user, register_user, update_user_name, 
    get_shield_count, is_shield_active,
    get_top_streak, get_top_messages_today,
    get_redemption_status, is_user_banned,
    ban_user, pardon_user
)
from core import (
    process_user_message, get_user_profile, 
    buy_shield, activate_shield,
    get_top_streak_text, get_top_messages_text,
    get_random_picture,
    get_random_phrase, load_phrases,
    admin_give_coins, admin_set_shield, admin_set_rank
)

logger = logging.getLogger(__name__)


async def chat_filter(message: types.Message) -> bool:
    if is_admin(message.from_user.id):
        return True
    
    if await is_user_banned(message.from_user.id):
        return False
    
    if message.chat.type == "private":
        user = await get_user(message.from_user.id)
        return user is not None
        
    return message.chat.id == CHAT_ID


async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    tg_name = message.from_user.full_name
    
    await register_user(user_id, username, tg_name)
    
    await message.answer(
        "🦊 **Привет! Я Дори.**\n\n"
        "Я слежу за активностью участников в чате. "
        "Общайся каждый день, чтобы удерживать свой стрик и повышать ранг! "
        "За длительное отсутствие твой стрик сгорает. Посмотреть команды: /help"
    )


async def cmd_help(message: types.Message):
    help_text = (
        "📋 **Команды лисы Дори:**\n\n"
        "👤 `/me` — Посмотреть свой профиль\n"
        "📝 `/name <Имя>` — Изменить имя в боте\n"
        "🛒 `/shop` — Магазин защиты\n"
        "⚡ `/activate_shield` — Активировать купленный щит\n"
        "🏆 `/top_streak` — Топ участников по дням\n"
        "💬 `/top_messages` — Топ по сообщениям за сегодня\n"
        "🔄 `/redemption` — Статус искупления стрика\n"
    )
    if is_admin(message.from_user.id):
        help_text += (
            "\n👑 **Админ-команды:**\n"
            "💰 `/give_coins @username <кол-во>` — Выдать монеты\n"
            "🛡️ `/set_shield @username <часы>` — Выдать временный щит\n"
            "🏆 `/rank @username <Имя Ранга>` — Установить и заморозить ранг\n"
            "❄️ `/rank @username сброс` — Разморозить авто-ранг\n"
            "🚫 `/dban @username` — Забанить в системе\n"
            "✅ `/dpardon @username` — Разбанить\n"
        )
    await message.answer(help_text)


async def cmd_me(message: types.Message):
    user_id = message.from_user.id
    profile_text = await get_user_profile(user_id)
    if profile_text:
        await message.answer(profile_text)
    else:
        await message.answer("❌ Твой профиль не найден. Напиши сначала любое сообщение в основном чате!")


async def cmd_name(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        return await message.answer("📝 Используй команду в формате:\n`/name ВашеНовоеИмя`")
        
    new_name = args[1].strip()
    if len(new_name) > 30:
        return await message.answer("⚠️ Имя слишком длинное! Максимум 30 символов.")
        
    await update_user_name(user_id, new_name)
    await message.answer(f"✅ Твое отображаемое имя изменено на: **{new_name}**")


async def cmd_shop(message: types.Message):
    text = (
        "🛒 **Магазин Дори**\n\n"
        "🛡️ **Щит защиты активности**\n"
        "Спасет твой стрик от обнуления на 36 часов, если ты забудешь написать в чат.\n"
        "💵 Стоимость: **100.0 монет**\n\n"
        "Для покупки используй: `/buy_shield`"
    )
    await message.answer(text)


async def cmd_buy_shield(message: types.Message):
    user_id = message.from_user.id
    success, text = await buy_shield(user_id)
    await message.answer(text)


async def cmd_activate_shield(message: types.Message):
    user_id = message.from_user.id
    success, text = await activate_shield(user_id)
    await message.answer(text)


async def cmd_top_streak(message: types.Message):
    text = await get_top_streak_text()
    await message.answer(text)


async def cmd_top_messages(message: types.Message):
    text = await get_top_messages_text()
    await message.answer(text)


async def cmd_redemption(message: types.Message):
    user_id = message.from_user.id
    status = await get_redemption_status(user_id)
    
    if status and status.get('active'):
        try:
            expires_at = datetime.fromisoformat(status['expires_at'])
            remaining = expires_at - datetime.now()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            
            if remaining.total_seconds() <= 0:
                await message.answer("💀 Время искупления вышло.")
                return
                
            await message.answer(
                f"🔄 **Режим восстановления стрика!**\n\n"
                f"Набрано сообщений: **{status['progress']}/{status['target']}**\n"
                f"Осталось времени: **{hours}ч {minutes}м**\n\n"
                f"Успей написать норму, чтобы вернуть свой стрик в {status['streak_to_restore']} дней!"
            )
        except Exception as e:
            logger.error(f"Ошибка парсинга даты искупления: {e}")
            await message.answer("❌ Ошибка получения данных.")
    else:
        await message.answer("ℹ️ У тебя нет активного процесса искупления стрика. Твой стрик в безопасности!")


# Административные хэндлеры
async def cmd_admin_give_coins(message: types.Message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("📝 Формат: `/give_coins @username <количество>`")
        
    identifier = args[1]
    try:
        amount = float(args[2])
        success, text = await admin_give_coins(message.from_user.id, identifier, amount)
        await message.answer(text)
    except ValueError:
        await message.answer("❌ Количество должно быть числом!")


async def cmd_admin_set_shield(message: types.Message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("📝 Формат: `/set_shield @username <часы>`")
        
    identifier = args[1]
    try:
        hours = int(args[2])
        success, text = await admin_set_shield(message.from_user.id, identifier, hours)
        await message.answer(text)
    except ValueError:
        await message.answer("❌ Время должно быть целым числом часов!")


async def cmd_admin_set_rank(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    # Ожидаем: /rank @username Имя Ранга (или сброс)
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("📝 Формат:\n`/rank @username <Имя Ранга>`\n`/rank @username сброс`")
        
    identifier = args[1].strip()
    rank_target = args[2].strip()
    
    success, text = await admin_set_rank(message.from_user.id, identifier, rank_target)
    await message.answer(text)


async def cmd_admin_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("📝 Формат: `/dban @username`")
        
    identifier = args[1].lstrip('@')
    from db import get_user_by_identifier
    user = await get_user_by_identifier(identifier)
    
    if user:
        await ban_user(user['user_id'])
        await message.answer(f"🚫 Пользователь {identifier} забанен в системе Дори.")
        try:
            await message.bot.send_message(user['user_id'], "🚫 **Вы забанены администратором бота.**")
        except:
            pass
    else:
        await message.answer(f"❌ Пользователь '{identifier}' не найден.")


async def cmd_admin_pardon(message: types.Message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("📝 Формат: `/dpardon @username`")
        
    identifier = args[1].lstrip('@')
    from db import get_user_by_identifier
    user = await get_user_by_identifier(identifier)
    
    if user:
        await pardon_user(user['user_id'])
        await message.answer(f"✅ Пользователь {identifier} разбанен!")
        try:
            await message.bot.send_message(user['user_id'], "🟢 **Вы разбанены администратором.**")
        except:
            pass
    else:
        await message.answer(f"❌ Пользователь '{identifier}' не найден.")


# Обработка всех сообщений (Подсчет стриков / Интеграция фраз)
async def handle_all_messages(message: types.Message):
    if not await chat_filter(message):
        return
        
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = message.from_user.username
    tg_name = message.from_user.full_name
    
    res = await process_user_message(user_id, chat_id, username, tg_name)
    
    if res.get('text'):
        # Если нужно прикрепить медиа по триггеру
        if res.get('need_media') and res.get('trigger'):
            pic = get_random_picture(res['trigger'], res.get('mood'))
            if pic and os.path.exists(pic):
                if res.get('send_to_dm'):
                    try:
                        await message.bot.send_photo(user_id, FSInputFile(pic), caption=res['text'])
                    except:
                        await message.reply(res['text'])
                else:
                    await message.reply_photo(FSInputFile(pic), caption=res['text'])
                return
                
        # Обычная отправка текста
        if res.get('send_to_dm'):
            try:
                await message.bot.send_message(user_id, res['text'])
            except:
                await message.reply(res['text'])
        else:
            await message.reply(res['text'])


def register_handlers(dp: Dispatcher, bot: Bot):
    # Пользовательские команды
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_me, Command("me"))
    dp.message.register(cmd_name, Command("name"))
    dp.message.register(cmd_shop, Command("shop"))
    dp.message.register(cmd_buy_shield, Command("buy_shield"))
    dp.message.register(cmd_activate_shield, Command("activate_shield"))
    dp.message.register(cmd_top_streak, Command("top_streak"))
    dp.message.register(cmd_top_messages, Command("top_messages"))
    dp.message.register(cmd_redemption, Command("redemption"))
    
    # Административные команды
    dp.message.register(cmd_admin_give_coins, Command("give_coins"))
    dp.message.register(cmd_admin_set_shield, Command("set_shield"))
    dp.message.register(cmd_admin_set_rank, Command("rank"))
    dp.message.register(cmd_admin_ban, Command("dban"))
    dp.message.register(cmd_admin_pardon, Command("dpardon"))
    
    # Общий текстовый обработчик
    dp.message.register(handle_all_messages, F.text)
