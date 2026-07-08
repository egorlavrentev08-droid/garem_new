# migrate.py

import aiosqlite
import os
import logging

from config import DB_PATH

logger = logging.getLogger(__name__)


async def run_migration():
    if not os.path.exists(DB_PATH):
        logger.warning(f"⚠️ База данных не найдена: {DB_PATH}")
        return False
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(users)")
        rows = await cursor.fetchall()
        existing_columns = [row[1] for row in rows]
        
        new_columns = {
            'is_banned': 'INTEGER DEFAULT 0',
            'last_ping': 'TEXT',
            'redemption_failed_notified': 'INTEGER DEFAULT 0',
        }
        
        logger.info("📋 Проверка колонок в таблице users...")
        
        for col_name, col_type in new_columns.items():
            if col_name not in existing_columns:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                    await db.commit()
                    logger.info(f"  ✅ Добавлена колонка: {col_name}")
                except Exception as e:
                    logger.error(f"  ❌ Ошибка: {e}")
            else:
                logger.info(f"  ⏭️ Колонка уже существует: {col_name}")
        
        await db.execute("UPDATE users SET is_banned = 0 WHERE is_banned IS NULL")
        await db.execute("UPDATE users SET redemption_failed_notified = 0 WHERE redemption_failed_notified IS NULL")
        await db.commit()
        
        logger.info("✅ Миграция завершена!")
        return True


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_migration())
