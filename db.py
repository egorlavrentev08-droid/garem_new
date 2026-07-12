# db.py

import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple

from config import DB_PATH, REDEMPTION_TARGET, REDEMPTION_HOURS

logger = logging.getLogger(__name__)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                telegram_username TEXT,
                tg_name TEXT,
                rank TEXT DEFAULT 'Без ранга',
                rank_frozen INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                streak_record INTEGER DEFAULT 0,
                coins REAL DEFAULT 0,
                shield_count INTEGER DEFAULT 0,
                shield_until TEXT,
                last_activity TEXT,
                messages_today INTEGER DEFAULT 0,
                streak_awarded_today INTEGER DEFAULT 0,
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                redemption_active INTEGER DEFAULT 0,
                redemption_target INTEGER DEFAULT 200,
                redemption_progress INTEGER DEFAULT 0,
                redemption_streak_to_restore INTEGER DEFAULT 0,
                redemption_expires_at TEXT,
                is_banned INTEGER DEFAULT 0,
                last_ping TEXT,
                redemption_failed_notified INTEGER DEFAULT 0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reward_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                reason TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        logger.info("🗄️ База данных успешно инициализирована.")


async def get_user(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_by_identifier(identifier: str) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Очищаем от собачки, если передан юзернейм
        clean_id = identifier.lstrip('@')
        
        # Ищем сначала по юзернейму
        cursor = await db.execute("SELECT * FROM users WHERE telegram_username = ?", (clean_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
            
        # Если не нашли, пробуем по ID
        if clean_id.isdigit():
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (int(clean_id),))
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None


async def register_user(user_id: int, username: str = None, tg_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        
        clean_username = username.lstrip('@') if username else None
        
        if not row:
            # Имя по умолчанию — это имя из Telegram, либо юзернейм
            default_name = tg_name or clean_username or str(user_id)
            await db.execute("""
                INSERT INTO users (user_id, telegram_username, tg_name, name, last_activity)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (user_id, clean_username, tg_name, default_name))
            await db.commit()
            logger.info(f"👤 Зарегистрирован новый пользователь: {default_name} ({user_id})")
        else:
            # Обновляем метаданные, если пользователь уже есть
            await db.execute("""
                UPDATE users 
                SET telegram_username = ?, tg_name = ? 
                WHERE user_id = ?
            """, (clean_username, tg_name, user_id))
            await db.commit()


async def update_user_name(user_id: int, new_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET name = ? WHERE user_id = ?", (new_name, user_id))
        await db.commit()


async def update_last_activity(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_activity = datetime('now') WHERE user_id = ?", (user_id,))
        await db.commit()


async def add_coins(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()


async def get_streak(user_id: int) -> int:
    user = await get_user(user_id)
    return user['streak'] if user else 0


async def increment_streak(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT streak, streak_record FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            new_streak = row['streak'] + 1
            new_record = max(new_streak, row['streak_record'])
            await db.execute("""
                UPDATE users SET streak = ?, streak_record = ? WHERE user_id = ?
            """, (new_streak, new_record, user_id))
            await db.commit()
            return new_streak
        return 0


async def update_streak(user_id: int, streak: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT streak_record FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        record = max(streak, row['streak_record']) if row else streak
        
        await db.execute("""
            UPDATE users SET streak = ?, streak_record = ? WHERE user_id = ?
        """, (streak, record, user_id))
        await db.commit()


async def increment_messages_today(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_shield_count(user_id: int) -> int:
    user = await get_user(user_id)
    return user['shield_count'] if user else 0


async def add_shield(user_id: int, count: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET shield_count = shield_count + ? WHERE user_id = ?", (count, user_id))
        await db.commit()


async def is_shield_active(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT shield_until FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row['shield_until']:
            try:
                until = datetime.fromisoformat(row['shield_until'])
                return datetime.now() < until
            except:
                return False
        return False


async def use_shield(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET shield_count = MAX(0, shield_count - 1) WHERE user_id = ?", (user_id,))
        await db.commit()


async def set_shield_until(user_id: int, hours: int):
    until_str = (datetime.now() + timedelta(hours=hours)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET shield_until = ? WHERE user_id = ?", (until_str, user_id))
        await db.commit()


async def deactivate_shield(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET shield_until = NULL WHERE user_id = ?", (user_id,))
        await db.commit()


async def start_redemption(user_id: int, streak_to_restore: int):
    expires_at = (datetime.now() + timedelta(hours=REDEMPTION_HOURS)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET 
                redemption_active = 1,
                redemption_target = ?,
                redemption_progress = 0,
                redemption_streak_to_restore = ?,
                redemption_expires_at = ?
            WHERE user_id = ?
        """, (REDEMPTION_TARGET, streak_to_restore, expires_at, user_id))
        await db.commit()


async def update_redemption_progress(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET redemption_progress = redemption_progress + 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_redemption_status(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT redemption_active as active, redemption_progress as progress, 
                   redemption_target as target, redemption_streak_to_restore as streak_to_restore,
                   redemption_expires_at as expires_at
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def complete_redemption(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT redemption_streak_to_restore, streak_record FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            streak = row['redemption_streak_to_restore']
            record = max(streak, row['streak_record'])
            await db.execute("""
                UPDATE users SET 
                    streak = ?,
                    streak_record = ?,
                    redemption_active = 0,
                    redemption_progress = 0
                WHERE user_id = ?
            """, (streak, record, user_id))
            await db.commit()


async def fail_redemption(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET 
                redemption_active = 0,
                redemption_progress = 0,
                streak = 0
            WHERE user_id = ?
        """, (user_id,))
        await db.commit()


async def get_top_streak(limit: int = 15) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT COALESCE(name, tg_name, telegram_username, CAST(user_id AS TEXT)) as display_name, streak 
            FROM users 
            WHERE is_banned = 0
            ORDER BY streak DESC LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_top_messages_today(limit: int = 15) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT COALESCE(name, tg_name, telegram_username, CAST(user_id AS TEXT)) as display_name, messages_today 
            FROM users 
            WHERE is_banned = 0 AND messages_today > 0
            ORDER BY messages_today DESC LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def add_reward_history(user_id: int, amount: float, reason: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO reward_history (user_id, amount, reason) VALUES (?, ?, ?)
        """, (user_id, amount, reason))
        await db.commit()


async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row and row['is_banned'] == 1


async def ban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def pardon_user(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        await db.commit()
        return True


async def get_last_ping(user_id: int) -> Optional[datetime]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT last_ping FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row['last_ping']:
            try:
                return datetime.fromisoformat(row['last_ping'])
            except:
                return None
        return None


async def update_last_ping(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_ping = datetime('now') WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_redemption_failed_notified(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT redemption_failed_notified FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row and row['redemption_failed_notified'] == 1


async def set_redemption_failed_notified(user_id: int, value: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET redemption_failed_notified = ? WHERE user_id = ?", (value, user_id))
        await db.commit()


async def reset_redemption_failed_notified(user_id: int):
    await set_redemption_failed_notified(user_id, 0)


async def get_inactive_users() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE last_activity IS NOT NULL AND is_banned = 0")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def award_daily_top() -> List[Tuple[Dict, int, float]]:
    winners = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM users 
            WHERE messages_today > 0 AND is_banned = 0
            ORDER BY messages_today DESC LIMIT 3
        """)
        rows = await cursor.fetchall()
        rewards = [500.0, 250.0, 100.0]
        
        for i, row in enumerate(rows):
            uid = row['user_id']
            amt = rewards[i]
            await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amt, uid))
            await db.execute("INSERT INTO reward_history (user_id, amount, reason) VALUES (?, ?, ?)", (uid, amt, f"Daily Top {i+1}"))
            winners.append((dict(row), i + 1, amt))
        await db.commit()
    return winners


async def award_weekly_top() -> List[Tuple[Dict, int, float]]:
    winners = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM users 
            WHERE streak > 0 AND is_banned = 0
            ORDER BY streak DESC LIMIT 3
        """)
        rows = await cursor.fetchall()
        
        for i, row in enumerate(rows):
            uid = row['user_id']
            amt = 1000.0
            await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amt, uid))
            await db.execute("INSERT INTO reward_history (user_id, amount, reason) VALUES (?, ?, ?)", (uid, amt, f"Weekly Top {i+1}"))
            winners.append((dict(row), i + 1, amt))
        await db.commit()
    return winners


async def reset_daily_messages():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET messages_today = 0, streak_awarded_today = 0")
        await db.commit()


async def check_expired_redemptions() -> List[int]:
    expired_ids = []
    now_str = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT user_id FROM users 
            WHERE redemption_active = 1 AND redemption_expires_at < ?
        """, (now_str,))
        rows = await cursor.fetchall()
        for row in rows:
            expired_ids.append(row['user_id'])
        
        if expired_ids:
            for uid in expired_ids:
                await db.execute("""
                    UPDATE users SET redemption_active = 0, redemption_progress = 0, streak = 0 
                    WHERE user_id = ?
                """, (uid,))
            await db.commit()
    return expired_ids
