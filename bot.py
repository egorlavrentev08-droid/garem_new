# bot.py

import logging
import random
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
        if not user:
            await message.answer(
                "🦊 Привет! Чтобы я тебя запомнил, "
                "напиши сначала в основном чате: @Gar3mDi"
            )
            return False
        return True
    
    if message.chat.id == CHAT_ID or message.chat.id == ADMIN_CHAT_ID:
        return True
    
    return False


async def delete_after_delay(bot: Bot, chat_id: int, message_id: int, delay: int = 7):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
        logger.info(f"🗑️ Сообщение {message_id} удалено через {delay} сек")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления сообщения {message_id}: {e}")


def register_handlers(dp: Dispatcher, bot: Bot):
    dp.message.register(cmd_start, Command("start"), chat_filter)
    dp.message.register(cmd_me, Command("me"), chat_filter)
    dp.message.register(cmd_me, Command("profile"), chat_filter)
    dp.message.register(cmd_name, Command("name"), chat_filter)
    dp.message.register(cmd_shop, Command("shop"), chat_filter)
    dp.message.register(cmd_top, Command("top"), chat_filter)
    dp.message.register(cmd_redemption, Command("redemption"), chat_filter)
    
    # Регистрация новой команды админа
    dp.message.register(cmd_admin_topfast, Command("topfast"), chat_filter)
    
    dp.message.register(cmd_admin_coins, Command("coins"), chat_filter)
    dp.message.register(cmd_admin_bypass, Command("bypass"), chat_filter)
    dp.message.register(cmd_admin_rank, Command("rank"), chat_filter)
    dp.message.register(cmd_admin_ban, Command("dban"), chat_filter)
    dp.message.register(cmd_admin_pardon, Command("dpardon"), chat_filter)
    
    dp.message.register(handle_all_messages, chat_filter)
    
    dp.callback_query.register(handle_shop_callback, F.data.in_(["buy_shield", "activate_shield"]))
    dp.callback_query.register(handle_top_callback, F.data.in_(["top_streak", "top_messages"]))
    
    # Колбэки для принудительного топа
    dp.callback_query.register(handle_topfast_choice, F.data.in_(["fast_top_messages", "fast_top_streaks"]))
    dp.callback_query.register(handle_topfast_confirm, F.data.in_(["confirm_fast_msg", "confirm_fast_str", "cancel_fast"]))


async def cmd_start(message: types.Message):
    tg_name = message.from_user.first_name
    if message.from_user.last_name:
        tg_name += f" {message.from_user.last_name}"

    user = await get_user(message.from_user.id)
    if not user:
        await register_user(message.from_user.id, message.from_user.username, tg_name)
        user = await get_user(message.from_user.id)
    
    if is_admin(message.from_user.id):
        await message.answer(
            "🦊 Добрый день, администратор!\n\n"
            "Ты зарегистрирован в системе.\n"
            "Используй /me для просмотра профиля."
        )
    else:
        await message.answer(
            "🦊 Привет! Я Dori — Архитектор Дисциплины!\n\n"
            "Ты зарегистрирован в системе.\n\n"
            "/me — профиль\n"
            "/shop — магазин\n"
            "/top — топы\n"
            "/redemption — статус искупления\n"
            "/name — сменить имя"
        )


async def cmd_me(message: types.Message):
    profile = await get_user_profile(message.from_user.id)
    if profile:
        await message.answer(profile)
    else:
        await message.answer("❌ Ты не зарегистрирован. Напиши в чате.")


async def cmd_name(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("📝 Используй: /name ТвоёИмя")
    
    new_name = args[1].strip()
    if len(new_name) > 50:
        return await message.answer("❌ Имя слишком длинное (макс. 50 символов).")
    
    success = await update_user_name(message.from_user.id, new_name)
    if success:
        await message.answer(f"✅ Теперь ты {new_name}!")
    else:
        await message.answer("❌ Это имя уже занято. Выбери другое.")


async def cmd_shop(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("❌ Ты не зарегистрирован.")
    
    shield_count = await get_shield_count(message.from_user.id)
    shield_active = await is_shield_active(message.from_user.id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🛡️ Купить щит (100 монет) [{shield_count} шт.]", 
            callback_data="buy_shield"
        )],
        [InlineKeyboardButton(
            text=f"⚡ Активировать щит (36 часов) {'✅' if shield_active else '❌'}", 
            callback_data="activate_shield"
        )]
    ])
    
    await message.answer(
        f"🛒 **Магазин**\n\n"
        f"💰 Монет: {user['coins']:.1f}\n"
        f"🛡️ Щитов в запасе: {shield_count} шт.\n"
        f"📊 Щит: {'🟢 Активен' if shield_active else '🔴 Не активен'}\n\n"
        f"💡 Щит защищает стрик от сброса на 36 часов",
        reply_markup=kb
    )


async def handle_shop_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "buy_shield":
        success, msg = await buy_shield(user_id)
        await callback.answer(msg, show_alert=True)
        if success:
            await callback.message.edit_text(
                f"✅ Щит куплен!\n\n"
                f"Используй 'Активировать щит', чтобы защитить стрик."
            )
    
    elif callback.data == "activate_shield":
        success, msg = await activate_shield(user_id)
        await callback.answer(msg, show_alert=True)
        if success:
            await callback.message.edit_text(
                f"⚡ Щит активирован на 36 часов!\n\n"
                f"Теперь ты защищён."
            )


async def cmd_top(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏆 Топ по стрикам", callback_data="top_streak"),
            InlineKeyboardButton(text="💬 Топ по сообщениям", callback_data="top_messages")
        ]
    ])
    await message.answer("📊 **Выбери топ:**", reply_markup=kb)


async def handle_top_callback(callback: types.CallbackQuery):
    await callback.answer()
    try:
        if callback.data == "top_streak":
            text = await get_top_streak_text()
        elif callback.data == "top_messages":
            text = await get_top_messages_text()
        else:
            return
        await callback.message.edit_text(text, parse_mode=None)
    except Exception as e:
        logger.error(f"Ошибка в handle_top_callback: {e}")
        try:
            if callback.data == "top_streak":
                text = await get_top_streak_text()
            else:
                text = await get_top_messages_text()
            await callback.message.answer(text)
        except Exception as e2:
            logger.error(f"Ошибка при отправке топа: {e2}")


async def cmd_redemption(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("❌ Ты не зарегистрирован.")
    
    redemption = await get_redemption_status(message.from_user.id)
    if not redemption or not redemption.get('active', False):
        return await message.answer(
            "❌ У тебя нет активного искупления.\n"
            "Оно появляется, если ты потерял стрик."
        )
    
    progress = redemption.get('progress', 0)
    target = redemption.get('target', 200)
    remaining = target - progress
    
    try:
        expires = datetime.fromisoformat(redemption['expires_at'])
        hours_left = (expires - datetime.now()).total_seconds() / 3600
    except:
        hours_left = 24
    
    text = (
        f"🔄 **Восстановление стрика**\n\n"
        f"Цель: {target} сообщений\n"
        f"Прогресс: {progress} сообщений\n"
        f"Осталось: {remaining} сообщений\n"
        f"Восстановится стрик: {redemption['streak_to_restore']} дней\n"
        f"⏳ Осталось: ~{int(hours_left)} часов\n\n"
        f"{'🔥 ДАВАЙ, ТЫ СМОЖЕШЬ!' if progress > 100 else '💪 ПИШИ БОЛЬШЕ!'}"
    )
    await message.answer(text)


# ============================================================
# РЕАЛИЗАЦИЯ ПРИНУДИТЕЛЬНОГО ТОПА ДЛЯ АДМИНОВ (/topfast)
# ============================================================
async def cmd_admin_topfast(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Топ по сообщениям", callback_data="fast_top_messages"),
            InlineKeyboardButton(text="🏆 Топ по стрикам", callback_data="fast_top_streaks")
        ]
    ])
    await message.answer(
        "⚙️ **Принудительное подведение итогов**\n"
        "Выберите, результаты какого топа вы хотите подвести прямо сейчас:", 
        reply_markup=kb
    )


async def handle_topfast_choice(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ Вы не админ!", show_alert=True)
    
    await callback.answer()
    
    if callback.data == "fast_top_messages":
        text = "❓ Вы уверены, что хотите **принудительно** подвести итоги топа по сообщениям и обнулить счетчик?"
        confirm_data = "confirm_fast_msg"
    else:
        text = "❓ Вы уверены, что хотите **принудительно** подвести итоги еженедельного топа по стрикам?"
        confirm_data = "confirm_fast_str"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=confirm_data),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_fast")
        ]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


async def handle_topfast_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ Вы не админ!", show_alert=True)
    
    await callback.answer()
    
    if callback.data == "cancel_fast":
        await callback.message.edit_text("❌ Действие отменено.")
        return
        
    from db import award_daily_top, award_weekly_top, reset_daily_messages
    
    # 1. Принудительный топ по СООБЩЕНИЯМ
    if callback.data == "confirm_fast_msg":
        winners = await award_daily_top()
        if winners:
            medals = ["🥇", "🥈", "🥉"]
            text = "📊 **ТОП СООБЩЕНИЙ ЗА ДЕНЬ**\n\n"
            for i, user in enumerate(winners):
                name = user.get('name', user.get('telegram_username', 'Кто-то'))
                reward = [500, 250, 100][i] if i < 3 else 0
                text += f"{medals[i]} **{name}** — +{reward} монет ({user['messages_today']} сообщений)\n"
            # Отправляем в основной чат
            await callback.bot.send_message(CHAT_ID, text)
        else:
            await callback.bot.send_message(CHAT_ID, "📊 **ТОП СООБЩЕНИЙ ЗА ДЕНЬ**\n\nСегодня никто не писал сообщения.")
        
        # СБРАСЫВАЕМ счетчик сообщений
        await reset_daily_messages()
        await callback.message.edit_text("✅ Топ по сообщениям успешно подведен и отправлен в основной чат!")
        
    # 2. Принудительный топ по СТРИКАМ
    elif callback.data == "confirm_fast_str":
        winners = await award_weekly_top()
        if winners:
            medals = ["🥇", "🥈", "🥉"]
            text = "🏆 **ЕЖЕНЕДЕЛЬНЫЙ ТОП**\n\n"
            for i, (user, position, coins) in enumerate(winners):
                name = user.get('name', user.get('telegram_username', 'Кто-то'))
                text += f"{medals[i]} **{name}** — {user['streak']} дней (+{coins} монет)\n"
            # Отправляем в основной чат
            await callback.bot.send_message(CHAT_ID, text)
        else:
            await callback.bot.send_message(CHAT_ID, "🏆 **ЕЖЕНЕДЕЛЬНЫЙ ТОП**\n\nНет активных стриков для награждения.")
            
        await callback.message.edit_text("✅ Топ по стрикам успешно подведен и отправлен в основной чат!")


async def handle_all_messages(message: types.Message):
    user_id = message.from_user.id
    
    if message.text and message.text.startswith('/'):
        return
    
    tg_name = message.from_user.first_name
    if message.from_user.last_name:
        tg_name += f" {message.from_user.last_name}"
        
    response = await process_user_message(
        user_id=user_id, 
        chat_id=message.chat.id, 
        username=message.from_user.username, 
        tg_name=tg_name
    )
    
    if not response or not response.get('text'):
        return
    
    reply_markup = None
    if message.chat.type == "private":
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗣 В чат", url="https://t.me/Gar3mDi")]
        ])
    
    if response.get('send_to_dm', False) or message.chat.type == "private":
        trigger = response.get('trigger', 'DAILY_GREETING')
        mood = response.get('mood', 'SARCASTIC')
        
        sent = None
        picture_path = get_random_picture(trigger, mood)
        if picture_path:
            try:
                sent = await message.bot.send_photo(
                    chat_id=user_id,
                    photo=FSInputFile(picture_path),
                    caption=response['text'],
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка отправки картинки в ЛС: {e}")
        
        if not sent:
            sent = await message.bot.send_message(
                chat_id=user_id,
                text=response['text'],
                reply_markup=reply_markup
            )
        return
    
    if random.random() > 0.2:
        return
    
    username = message.from_user.username
    if not username:
        username = message.from_user.first_name or "Друг"
    
    final_text = f"@{username}, {response['text']}"
    sent_message = await message.answer(final_text, reply_markup=reply_markup)
    
    if sent_message and message.chat.type != "private":
        asyncio.create_task(delete_after_delay(
            message.bot,
            sent_message.chat.id,
            sent_message.message_id,
            7
        ))


async def cmd_admin_coins(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        return await message.answer(
            "📝 Используй:\n"
            "/coins give @username 10\n"
            "/coins take @username 10\n"
            "Или с ответом на сообщение:\n"
            "/coins give 10\n"
            "/coins take 10"
        )
    
    action = parts[1].lower()
    if action not in ['give', 'take']:
        return await message.answer("❌ Используй: /coins give @username N или /coins take @username N")
    
    if len(parts) >= 3 and parts[2].startswith('@'):
        identifier = parts[2][1:]
        try:
            amount = float(parts[3])
        except (IndexError, ValueError):
            return await message.answer("❌ Сумма должна быть числом.")
    else:
        if message.reply_to_message:
            identifier = str(message.reply_to_message.from_user.id)
            try:
                amount = float(parts[2])
            except (IndexError, ValueError):
                return await message.answer("❌ Сумма должна быть числом.")
        else:
            return await message.answer("❌ Укажи пользователя (@username) или ответь на сообщение.")
    
    if amount <= 0:
        return await message.answer("❌ Сумма должна быть больше 0.")
    
    if action == 'take':
        amount = -amount
    
    success, msg = await admin_give_coins(message.from_user.id, identifier, amount)
    await message.answer(msg)


async def cmd_admin_bypass(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer(
            "📝 Используй:\n"
            "/bypass @username часы\n"
            "Или с ответом на сообщение:\n"
            "/bypass часы"
        )
    
    if parts[1].startswith('@') or not parts[1].isdigit():
        identifier = parts[1].lstrip('@')
        try:
            hours = int(parts[2])
        except (IndexError, ValueError):
            return await message.answer("❌ Часы должны быть числом (0-240).")
    else:
        if message.reply_to_message:
            identifier = str(message.reply_to_message.from_user.id)
            try:
                hours = int(parts[1])
            except ValueError:
                return await message.answer("❌ Часы должны быть числом (0-240).")
        else:
            return await message.answer("❌ Укажи пользователя (@username) или ответь на сообщение.")
    
    if hours < 0 or hours > 240:
        return await message.answer("❌ Часы должны быть от 0 до 240.")
    
    success, msg = await admin_set_shield(message.from_user.id, identifier, hours)
    await message.answer(msg)


async def cmd_admin_rank(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        return await message.answer(
            "📝 Используй:\n"
            "/rank @username Новичок\n\n"
            "Доступные ранги:\n"
            "Без ранга, Новичок, Кандидат, Знакомый,\n"
            "Хороший, Душа, Старожил, Гордость,\n"
            "Авторитет, Незаменимый"
        )
    
    identifier = parts[1].lstrip('@')
    rank_name = parts[2].strip()
    
    success, msg = await admin_set_rank(message.from_user.id, identifier, rank_name)
    await message.answer(msg)


async def cmd_admin_ban(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    user_id = None
    args = message.text.split()
    
    if len(args) >= 2:
        identifier = args[1].lstrip('@')
        from db import get_user_by_identifier
        user = await get_user_by_identifier(identifier)
        if user:
            user_id = user['user_id']
        else:
            return await message.answer(f"❌ Пользователь '{identifier}' не найден.")
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        return await message.answer(
            "📝 Используй:\n"
            "/dban @username\n"
            "Или с ответом на сообщение:\n"
            "/dban"
        )
    
    if is_admin(user_id):
        return await message.answer("❌ Нельзя забанить админа!")
    
    if await is_user_banned(user_id):
        return await message.answer("❌ Пользователь уже забанен.")
    
    success = await ban_user(user_id)
    if success:
        user = await get_user(user_id)
        name = user.get('name') or user.get('tg_name') or user.get('telegram_username') or str(user_id)
        await message.answer(f"✅ **{name}** забанен!")
        try:
            await message.bot.send_message(
                user_id,
                "🚫 **Вы забанены!**\nДля восстановления обратитесь к администратору."
            )
        except:
            pass


async def cmd_admin_pardon(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    user_id = None
    args = message.text.split()
    
    if len(args) >= 2:
        identifier = args[1].lstrip('@')
        from db import get_user_by_identifier
        user = await get_user_by_identifier(identifier)
        if user:
            user_id = user['user_id']
        else:
            return await message.answer(f"❌ Пользователь '{identifier}' не найден.")
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        return await message.answer(
            "📝 Используй:\n"
            "/dpardon @username\n"
            "Или с ответом на сообщение:\n"
            "/dpardon"
        )
    
    success = await pardon_user(user_id)
    if success:
        user = await get_user(user_id)
        name = user.get('name') or user.get('tg_name') or user.get('telegram_username') or str(user_id)
        await message.answer(f"✅ **{name}** разбанен!")
        try:
            await message.bot.send_message(
                user_id,
                "🟢 **Вы разбанены!**\nДобро пожаловать обратно."
            )
        except:
            pass
    else:
        await message.answer("❌ Пользователь не был забанен.")
