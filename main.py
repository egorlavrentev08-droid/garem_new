# main.py

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, CHAT_ID, ADMIN_IDS, DB_PATH
from db import init_db, check_expired_redemptions
from core import load_phrases, check_inactive_users, handle_inactive_user, execute_daily_top, execute_weekly_top
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
    
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Зарегистрироваться"),
        types.BotCommand(command="me", description="Профиль"),
        types.BotCommand(command="name", description="Сменить имя"),
        types.BotCommand(command="shop", description="Магазин"),
        types.BotCommand(command="top", description="Топы"),
        types.BotCommand(command="redemption", description="Статус искупления"),
    ])
    
    # Запускаем планировщик как фоновую задачу
    asyncio.create_task(scheduler_loop(bot))
    
    logger.info("🚀 Бот успешно запущен и готов к работе!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


async def scheduler_loop(bot: Bot):
    logger.info("⏰ Планировщик запущен")
    
    # Жестко задаем часовой пояс МСК (UTC+3)
    MSK = timezone(timedelta(hours=3))
    
    last_inactive_check = datetime.now(MSK)
    
    # Флаги-предохранители: гарантируют, что задача выполнится ровно 1 раз
    last_daily_run = None
    last_weekly_run = None
    last_redemption_run = None
    
    while True:
        try:
            now = datetime.now(MSK)
            current_date = now.strftime("%Y-%m-%d")
            current_hour = now.strftime("%Y-%m-%d %H")
            
            # 1. Проверка неактивных пользователей (каждые 30 минут)
            if (now - last_inactive_check).total_seconds() >= 1800:
                last_inactive_check = now
                asyncio.create_task(check_inactive_task(bot))
            
            # 2. Ежедневный топ сообщений (Строго в 00:00 МСК)
            if now.hour == 0 and now.minute == 0:
                # Предохранитель от повторений в эту минуту
                if last_daily_run != current_date:
                    last_daily_run = current_date
                    asyncio.create_task(daily_reset_task(bot))
            
            # 3. Еженедельный топ стриков (Воскресенье, строго в 23:00 МСК)
            # now.weekday() == 6 — это воскресенье
            if now.weekday() == 6 and now.hour == 23 and now.minute == 0:
                # Предохранитель от повторений в эту минуту
                if last_weekly_run != current_date:
                    last_weekly_run = current_date
                    asyncio.create_task(weekly_reward_task(bot))
            
            # 4. Проверка искуплений (Каждый час ровно в 00 минут)
            if now.minute == 0:
                # Предохранитель от повторений (раз в час)
                if last_redemption_run != current_hour:
                    last_redemption_run = current_hour
                    asyncio.create_task(check_redemptions_task(bot))
            
        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике: {e}")
        
        # Спим 10 секунд. Это идеальный баланс: 
        # не нагружает процессор и бот физически не сможет пропустить нужную минуту.
        await asyncio.sleep(10)


async def check_inactive_task(bot: Bot):
    logger.info("⏳ Проверка неактивных пользователей...")
    inactive_users = await check_inactive_users()
    
    for user_id, days in inactive_users:
        res = await handle_inactive_user(user_id, days)
        if res:
            try:
                from db import get_user
                user = await get_user(user_id)
                if user:
                    name = user.get('name', user.get('telegram_username', 'Кто-то'))
                    
                    # Личное сообщение пользователю
                    await bot.send_message(user_id, res['private_text'])
                    
                    # Сообщение в общий чат
                    await bot.send_message(CHAT_ID, res['chat_text'])
                    
                    if res.get('lost_streak'):
                        await bot.send_message(
                            CHAT_ID,
                            f"😱 **{name}** потерял стрик!\n"
                            f"Но может восстановить — 200 сообщений за 24 часа. 👀"
                        )
            except Exception as e:
                logger.error(f"❌ Ошибка отправки {user_id}: {e}")


async def daily_reset_task(bot: Bot):
    logger.info("🔄 Ежедневный сброс")
    await execute_daily_top(bot)
    logger.info("✅ Ежедневный сброс завершён")


async def weekly_reward_task(bot: Bot):
    logger.info("🔄 Еженедельные награды")
    await execute_weekly_top(bot)
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
                    CHAT_ID,
                    f"⏰ **{name}** не успел восстановить стрик. Начинает с нуля. 😈"
                )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления об искуплении для {user_id}: {e}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🦊 Бот остановлен")
