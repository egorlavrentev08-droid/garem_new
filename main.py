# main.py

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
from migrate import run_migration

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🦊 Запуск Dori...")
    
    await run_migration()
    
    load_phrases()
    
    await init_db()
    
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
    dp = Dispatcher()
    
    register_handlers(dp, bot)
    
    # ============================================================
    # НАСТРОЙКА КОМАНД ДЛЯ ПРЕДЛОЖКИ (ПРИ ВВОДЕ /)
    # ============================================================
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Зарегистрироваться"),
        types.BotCommand(command="me", description="Профиль"),
        types.BotCommand(command="name", description="Сменить имя"),
        types.BotCommand(command="shop", description="Магазин"),
        types.BotCommand(command="top", description="Топы"),
        types.BotCommand(command="redemption", description="Статус искупления"),
    ])
    
    asyncio.create_task(scheduler_loop(bot))
    
    logger.info("✅ Бот запущен!")
    await dp.start_polling(bot)


async def scheduler_loop(bot: Bot):
    logger.info("⏰ Планировщик запущен")
    
    last_inactive_check = datetime.now() - timedelta(hours=1)
    last_daily_reset = datetime.now() - timedelta(days=1)
    last_weekly_reset = datetime.now() - timedelta(days=7)
    last_redemption_check = datetime.now() - timedelta(hours=1)
    
    while True:
        try:
            now = datetime.now()
            
            # Проверка неактивных — каждые 30 минут
            if (now - last_inactive_check).total_seconds() >= 1800:
                last_inactive_check = now
                await check_inactive_task(bot)
            
            # Ежедневный сброс — если прошло больше 23 часов, и сейчас 00:00-00:05
            if (now - last_daily_reset).total_seconds() >= 82800:  # 23 часа
                if now.hour == 0 and now.minute <= 5:
                    last_daily_reset = now
                    await daily_reset_task(bot)
            
            # Еженедельный сброс — если прошло больше 6 дней, и сейчас воскресенье 23:00-23:05
            if (now - last_weekly_reset).total_seconds() >= 518400:  # 6 дней
                if now.weekday() == 6 and now.hour == 23 and now.minute <= 5:
                    last_weekly_reset = now
                    await weekly_reward_task(bot)
            
            # Проверка искуплений — каждую минуту
            if now.minute == 0:
                last_redemption_check = now
                await check_redemptions_task(bot)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике: {e}")
        
        await asyncio.sleep(30)


async def check_inactive_task(bot: Bot):
    inactive = await check_inactive_users()
    
    if not inactive:
        return
    
    logger.info(f"📊 Найдено неактивных: {len(inactive)}")
    
    for data in inactive:
        user = data['user']
        user_id = user['user_id']
        trigger = data['trigger']
        mood = data['mood']
        
        result = await handle_inactive_user(user_id, trigger, mood)
        
        if result and result.get('text'):
            kb = None
            try:
                kb = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🗣 В чат", url="https://t.me/Gar3mDi")]
                ])
            except:
                pass
            
            try:
                await bot.send_message(
                    user_id,
                    result['text'],
                    reply_markup=kb
                )
                logger.info(f"📨 Уведомление отправлено {user_id}")
                
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
    logger.info("🔄 Ежедневный сброс")
    
    winners = await award_daily_top()
    if winners:
        medals = ["🥇", "🥈", "🥉"]
        text = "📊 **ТОП СООБЩЕНИЙ ЗА ДЕНЬ**\n\n"
        
        for i, user in enumerate(winners):
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            reward = [500, 250, 100][i] if i < 3 else 0
            text += f"{medals[i]} **{name}** — +{reward} монет ({user['messages_today']} сообщений)\n"
        
        await bot.send_message(ADMIN_CHAT_ID, text)
    
    await reset_daily_messages()
    logger.info("✅ Ежедневный сброс завершён")


async def weekly_reward_task(bot: Bot):
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
