# main.py - ТОЧКА ВХОДА

import asyncio
import logging
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, ADMIN_CHAT_ID, ADMIN_IDS, DB_PATH
from db import init_db, award_daily_top, award_weekly_top, reset_daily_messages, check_expired_redemptions
from core import load_phrases, check_inactive_users, handle_inactive_user, get_random_phrase
from bot import register_handlers
from test import is_test_mode, get_test_status

# ============================================================
# 1. НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# 2. ЗАПУСК БОТА
# ============================================================

async def main():
    """Главная функция"""
    
    # Инициализация
    logger.info("🦊 Запуск Dori...")
    
    # Загружаем фразы
    load_phrases()
    
    # Инициализируем БД
    await init_db()
    
    # Создаём бота и диспетчер
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
    dp = Dispatcher()
    
    # Регистрируем хендлеры
    register_handlers(dp, bot)
    
    # Запускаем фоновые задачи
    asyncio.create_task(scheduler_loop(bot))
    
    # Статус тестового режима
    if is_test_mode():
        status = get_test_status()
        logger.warning(f"⚠️ ТЕСТОВЫЙ РЕЖИМ ВКЛЮЧЁН! Ускорение x{status['multiplier']}")
    
    # Запускаем бота
    logger.info("✅ Бот запущен!")
    await dp.start_polling(bot)


# ============================================================
# 3. ПЛАНИРОВЩИК (ФОНОВЫЙ)
# ============================================================

async def scheduler_loop(bot: Bot):
    """Фоновый цикл планировщика"""
    logger.info("⏰ Планировщик запущен")
    
    # Время последней проверки
    last_inactive_check = datetime.now() - timedelta(hours=1)
    last_daily_reset = datetime.now() - timedelta(days=1)
    last_weekly_reset = datetime.now() - timedelta(days=7)
    
    while True:
        try:
            now = datetime.now()
            
            # --- 1. ПРОВЕРКА НЕАКТИВА (каждые 30 минут) ---
            if (now - last_inactive_check).total_seconds() >= 1800:
                last_inactive_check = now
                await check_inactive_task(bot)
            
            # --- 2. ЕЖЕДНЕВНЫЙ СБРОС (00:00 МСК) ---
            if now.hour == 0 and now.minute == 0:
                if (now - last_daily_reset).days >= 1:
                    last_daily_reset = now
                    await daily_reset_task(bot)
            
            # --- 3. ЕЖЕНЕДЕЛЬНЫЙ ТОП (воскресенье 23:59) ---
            if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
                if (now - last_weekly_reset).days >= 7:
                    last_weekly_reset = now
                    await weekly_reward_task(bot)
            
            # --- 4. ПРОВЕРКА ИСКУПЛЕНИЙ (каждый час) ---
            if now.minute == 0:
                await check_redemptions_task(bot)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике: {e}")
        
        # Спим 30 секунд
        await asyncio.sleep(30)


# ============================================================
# 4. ЗАДАЧИ ПЛАНИРОВЩИКА
# ============================================================

async def check_inactive_task(bot: Bot):
    """Проверяет неактивных пользователей"""
    inactive = await check_inactive_users()
    
    if not inactive:
        return
    
    logger.info(f"📊 Найдено неактивных: {len(inactive)}")
    
    for data in inactive:
        user = data['user']
        user_id = user['user_id']
        trigger = data['trigger']
        mood = data['mood']
        
        # Обрабатываем
        result = await handle_inactive_user(user_id, trigger, mood)
        
        if result and result.get('text'):
            # Кнопка "В чат"
            kb = None
            try:
                kb = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🗣 В чат", url="https://t.me/Gar3mDi")]
                ])
            except:
                pass
            
            # Отправляем в ЛС
            try:
                await bot.send_message(
                    user_id,
                    result['text'],
                    reply_markup=kb
                )
                logger.info(f"📨 Уведомление отправлено {user_id}")
                
                # Если стрик сброшен — оповещаем в АДМИНСКИЙ чат
                if "сброшен" in result['text']:
                    name = user.get('name', user.get('telegram_username', 'Кто-то'))
                    await bot.send_message(
                        ADMIN_CHAT_ID,
                        f"😱 **{name}** потерял стрик!\n"
                        f"Но может восстановить — {200} сообщений за 24 часа. 👀"
                    )
            except Exception as e:
                logger.error(f"❌ Ошибка отправки {user_id}: {e}")


async def daily_reset_task(bot: Bot):
    """Ежедневный сброс и награды"""
    logger.info("🔄 Ежедневный сброс")
    
    # Награждаем лидера
    winner = await award_daily_top()
    if winner:
        name = winner.get('name', winner.get('telegram_username', 'Кто-то'))
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"🌟 **{name}** — лидер дня! +100 монет! 🪙"
        )
    
    # Сбрасываем счётчики
    await reset_daily_messages()
    logger.info("✅ Ежедневный сброс завершён")


async def weekly_reward_task(bot: Bot):
    """Еженедельные награды"""
    logger.info("🔄 Еженедельные награды")
    
    winners = await award_weekly_top()
    if winners:
        medals = ["🥇", "🥈", "🥉"]
        text = "🏆 **ЕЖЕНЕДЕЛЬНЫЙ ТОП**\n\n"
        
        for i, (user, position, coins) in enumerate(winners):
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            text += f"{medals[i]} **{name}** — {user['streak']} дней (+{coins} монет)\n"
        
        await bot.send_message(ADMIN_CHAT_ID, text)
    
    logger.info("✅ Еженедельные награды завершены")


async def check_redemptions_task(bot: Bot):
    """Проверяет просроченные искупления"""
    expired = await check_expired_redemptions()
    
    for user_id in expired:
        try:
            from db import get_user
            user = await get_user(user_id)
            if user:
                name = user.get('name', user.get('telegram_username', 'Кто-то'))
                
                await bot.send_message(
                    user_id,
                    f"💀 Время вышло. Стрик не восстановлен. Начинай с нуля! 💪"
                )
                
                await bot.send_message(
                    ADMIN_CHAT_ID,
                    f"⏰ **{name}** не успел восстановить стрик. Начинает с нуля. 😈"
                )
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке искупления {user_id}: {e}")


# ============================================================
# 5. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
