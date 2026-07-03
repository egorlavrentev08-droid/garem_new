# bot.py - РЕГИСТРАЦИЯ ХЕНДЛЕРОВ И ФИЛЬТРЫ

import logging
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from config import (
    CHAT_ID, ADMIN_CHAT_ID, ADMIN_IDS, 
    is_admin, is_allowed_chat, get_rank_by_streak
)
from db import (
    get_user, register_user, update_user_name, 
    get_shield_count, is_shield_active,
    get_top_streak, get_top_messages_today,
    get_redemption_status
)
from core import (
    process_user_message, get_user_profile, 
    buy_shield, activate_shield,
    get_top_streak_text, get_top_messages_text,
    get_random_picture, get_random_meme,
    get_random_phrase, load_phrases,
    add_phrase_from_text, delete_phrase, get_all_phrases,
    admin_give_coins, admin_set_shield, admin_set_rank
)

logger = logging.getLogger(__name__)


# ============================================================
# 1. ФИЛЬТРЫ
# ============================================================

async def chat_filter(message: types.Message) -> bool:
    """
    Фильтр: бот работает ТОЛЬКО в админском чате и ЛС
    """
    # 1. ЛС — проверяем регистрацию
    if message.chat.type == "private":
        user = await get_user(message.from_user.id)
        if not user:
            await message.answer(
                "🦊 Привет! Чтобы я тебя запомнил, "
                "напиши сначала в основном чате: @Gar3mDi"
            )
            return False
        return True
    
    # 2. ТОЛЬКО админский чат (НЕ основной!)
    if message.chat.id == ADMIN_CHAT_ID:
        return True
    
    # 3. Все остальные чаты — игнор
    return False


# ============================================================
# 2. РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ============================================================

def register_handlers(dp: Dispatcher, bot: Bot):
    """Регистрирует все хендлеры"""
    
    dp.message.register(cmd_start, Command("start"), chat_filter)
    dp.message.register(cmd_me, Command("me"), chat_filter)
    dp.message.register(cmd_me, Command("profile"), chat_filter)
    dp.message.register(cmd_name, Command("name"), chat_filter)
    dp.message.register(cmd_shop, Command("shop"), chat_filter)
    dp.message.register(cmd_top_streak, Command("top_streak"), chat_filter)
    dp.message.register(cmd_top_messages, Command("top_messages"), chat_filter)
    dp.message.register(cmd_top_messages, Command("top_sms"), chat_filter)
    dp.message.register(cmd_redemption, Command("redemption"), chat_filter)
    
    dp.message.register(cmd_admin_coins, Command("coins"), chat_filter)
    dp.message.register(cmd_admin_bypass, Command("bypass"), chat_filter)
    dp.message.register(cmd_admin_rank, Command("rank"), chat_filter)
    dp.message.register(cmd_admin_addphrase, Command("addphrase"), chat_filter)
    dp.message.register(cmd_admin_delphrase, Command("delphrase"), chat_filter)
    dp.message.register(cmd_admin_phrases, Command("phrases"), chat_filter)
    
    dp.message.register(handle_all_messages, chat_filter)
    
    dp.callback_query.register(handle_shop_callback, F.data.in_(["buy_shield", "activate_shield"]))
    dp.callback_query.register(handle_phrase_confirm, F.data == "phrase_confirm")
    dp.callback_query.register(handle_phrase_cancel, F.data == "phrase_cancel")


# ============================================================
# 3. ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
# ============================================================

async def cmd_start(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user:
        await register_user(message.from_user.id, message.from_user.username)
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
            "/top_streak — топ стриков\n"
            "/top_sms — топ сообщений за сегодня\n"
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


async def cmd_top_streak(message: types.Message):
    text = await get_top_streak_text()
    await message.answer(text)


async def cmd_top_messages(message: types.Message):
    text = await get_top_messages_text()
    await message.answer(text)


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
# 4. ОБРАБОТКА ВСЕХ СООБЩЕНИЙ
# ============================================================

async def handle_all_messages(message: types.Message):
    """Обрабатывает все сообщения в разрешённых чатах"""
    user_id = message.from_user.id
    
    if message.text and message.text.startswith('/'):
        return
    
    response = await process_user_message(user_id, message.chat.id)
    
    if not response or not response.get('text'):
        return
    
    # Кнопка "В чат" (для ЛС)
    reply_markup = None
    if message.chat.type == "private":
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗣 В чат", url="https://t.me/Gar3mDi")]
        ])
    
    # ============================================================
    # ЕСЛИ send_to_dm = True — ОТПРАВЛЯЕМ В ЛИЧКУ!
    # ============================================================
    if response.get('send_to_dm', False):
        try:
            # Отправляем в ЛС пользователя
            await message.bot.send_message(
                user_id,
                response['text'],
                reply_markup=reply_markup
            )
            logger.info(f"📨 Отправлено в ЛС {user_id}: {response['text'][:50]}...")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в ЛС {user_id}: {e}")
        return  # НЕ ОТВЕЧАЕМ В ЧАТ
    
    # ============================================================
    # ИНАЧЕ — ОТВЕЧАЕМ В ЧАТ
    # ============================================================
    
    use_meme = response.get('is_meme', False) or (random.random() < 0.2)
    trigger = response.get('trigger', 'DAILY_GREETING')
    mood = response.get('mood', 'SARCASTIC')
    
    if use_meme:
        meme_path = get_random_meme(trigger, mood)
        if meme_path:
            try:
                await message.answer_photo(
                    photo=FSInputFile(meme_path),
                    caption=response['text'],
                    reply_markup=reply_markup
                )
                return
            except Exception as e:
                logger.error(f"Ошибка отправки мема: {e}")
    else:
        picture_path = get_random_picture(trigger, mood)
        if picture_path:
            try:
                await message.answer_photo(
                    photo=FSInputFile(picture_path),
                    caption=response['text'],
                    reply_markup=reply_markup
                )
                return
            except Exception as e:
                logger.error(f"Ошибка отправки картинки: {e}")
    
    await message.answer(response['text'], reply_markup=reply_markup)


# ============================================================
# 5. АДМИН-КОМАНДЫ
# ============================================================

async def cmd_admin_coins(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        return await message.answer(
            "📝 Используй:\n"
            "/coins @username 10\n"
            "/coins -@username 10\n"
            "Или с ответом на сообщение:\n"
            "/coins 10"
        )
    
    if parts[1].startswith('@'):
        identifier = parts[1][1:]
        try:
            amount = float(parts[2])
        except ValueError:
            return await message.answer("❌ Сумма должна быть числом.")
    else:
        if message.reply_to_message:
            identifier = str(message.reply_to_message.from_user.id)
            try:
                amount = float(parts[1])
            except ValueError:
                return await message.answer("❌ Сумма должна быть числом.")
        else:
            return await message.answer("❌ Укажи пользователя или ответь на сообщение.")
    
    success, msg = await admin_give_coins(message.from_user.id, identifier, amount)
    await message.answer(msg)


async def cmd_admin_bypass(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        return await message.answer(
            "📝 Используй:\n"
            "/bypass @username 36\n"
            "Или с ответом на сообщение:\n"
            "/bypass 36"
        )
    
    if parts[1].startswith('@'):
        identifier = parts[1][1:]
        try:
            hours = int(parts[2])
        except ValueError:
            return await message.answer("❌ Часы должны быть числом.")
    else:
        if message.reply_to_message:
            identifier = str(message.reply_to_message.from_user.id)
            try:
                hours = int(parts[1])
            except ValueError:
                return await message.answer("❌ Часы должны быть числом.")
        else:
            return await message.answer("❌ Укажи пользователя или ответь на сообщение.")
    
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


async def cmd_admin_addphrase(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    text = message.text.replace('/addphrase', '').strip()
    if not text:
        return await message.answer(
            "📝 Используй: /addphrase !₽ Текст фразы\n\n"
            "Триггеры: ! (приветствие), ? (1 день), ¡ (3+ дней)\n"
            "          ~ (возвращение), ∆ (ранг), % (достижение)\n\n"
            "Настроения: ₽ (саркастичное), £ (злое), $ (гневное)"
        )
    
    success, msg, parsed = add_phrase_from_text(text)
    if not success:
        return await message.answer(msg)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Сохранить", callback_data="phrase_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="phrase_cancel")
        ]
    ])
    
    global _pending_phrase
    _pending_phrase = parsed
    
    await message.answer(
        f"📝 **Фраза принята!**\n\n"
        f"Триггер: {parsed['trigger']}\n"
        f"Настроение: {parsed['mood']}\n"
        f"Текст: {parsed['text']}\n\n"
        f"Всё верно?",
        reply_markup=kb
    )


_pending_phrase = None


async def handle_phrase_confirm(callback: types.CallbackQuery):
    global _pending_phrase
    if not _pending_phrase:
        return await callback.answer("❌ Сессия истекла", show_alert=True)
    
    parsed = _pending_phrase
    _pending_phrase = None
    
    success, msg, _ = add_phrase_from_text(f"{list(TRIGGER_SYMBOLS.keys())[list(TRIGGER_SYMBOLS.values()).index(parsed['trigger'])]}{list(MOOD_SYMBOLS.keys())[list(MOOD_SYMBOLS.values()).index(parsed['mood'])]} {parsed['text']}")
    
    await callback.message.edit_text(f"✅ Фраза добавлена!\n\n{parsed['text']}")
    await callback.answer("✅ Сохранено!")


async def handle_phrase_cancel(callback: types.CallbackQuery):
    global _pending_phrase
    _pending_phrase = None
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


async def cmd_admin_delphrase(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    text = message.text.replace('/delphrase', '').strip()
    if not text:
        return await message.answer("📝 Используй: /delphrase Текст_фразы")
    
    all_phrases = get_all_phrases()
    found = None
    
    for p in all_phrases:
        if text.lower() in p['text'].lower():
            found = p
            break
    
    if not found:
        return await message.answer(f"❌ Фраза не найдена: {text}")
    
    success = delete_phrase(found['trigger'], found['text'])
    if success:
        await message.answer(f"✅ Фраза удалена:\n{found['text']}")
    else:
        await message.answer("❌ Ошибка при удалении")


async def cmd_admin_phrases(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    all_phrases = get_all_phrases()
    if not all_phrases:
        return await message.answer("📭 Фраз пока нет.")
    
    text = "📚 **Список фраз**\n\n"
    for i, p in enumerate(all_phrases[:30], 1):
        text += f"{i}. [{p['trigger']}:{p['mood']}] {p['text'][:50]}...\n"
    
    if len(all_phrases) > 30:
        text += f"\n... и ещё {len(all_phrases) - 30} фраз"
    
    await message.answer(text)
