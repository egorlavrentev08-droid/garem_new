# db.py

import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

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
            CREATE TABLE IF NOT EXISTS rewards_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                reward_type TEXT,
                position INTEGER,
                coins INTEGER,
                streak INTEGER,
                awarded_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_streak ON users(streak)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_messages_today ON users(messages_today)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity)")
        
        await db.commit()
        logger.info("✅ База данных инициализирована")


async def register_user(user_id: int, username: str = None, tg_name: str = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = await cursor.fetchone()
        
        if exists:
            # Обновляем юзернейм и реальное имя из ТГ при каждом сообщении
            await db.execute(
                "UPDATE users SET telegram_username = ?, tg_name = ? WHERE user_id = ?", 
                (username, tg_name, user_id)
            )
            await db.commit()
            return False
        
        # Для новых пользователей поле name оставляем NULL, чтобы работал приоритет
        await db.execute(
            """INSERT INTO users (user_id, name, telegram_username, tg_name, last_activity) 
               VALUES (?, NULL, ?, ?, datetime('now'))""",
            (user_id, username, tg_name)
        )
        await db.commit()
        logger.info(f"✅ Новый пользователь: {tg_name or username or str(user_id)} (ID: {user_id})")
        return True


async def get_user(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_by_identifier(identifier: str) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        if identifier.isdigit():
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (int(identifier),))
            row = await cursor.fetchone()
            if row:
                return dict(row)
        
        clean = identifier.lstrip('@').lower()
        cursor = await db.execute(
            "SELECT * FROM users WHERE LOWER(telegram_username) = ?", 
            (clean,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        
        cursor = await db.execute("SELECT * FROM users WHERE name = ?", (identifier,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        
        return None


async def update_user_name(user_id: int, new_name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE name = ?", (new_name,))
        exists = await cursor.fetchone()
        if exists:
            return False
        
        await db.execute("UPDATE users SET name = ? WHERE user_id = ?", (new_name, user_id))
        await db.commit()
        return True


async def update_last_activity(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_activity = datetime('now') WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


async def add_coins(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()


async def get_coins(user_id: int) -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0.0


async def add_shield(user_id: int, count: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET shield_count = shield_count + ? WHERE user_id = ?",
            (count, user_id)
        )
        await db.commit()


async def use_shield(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT shield_count FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0] > 0:
            await db.execute(
                "UPDATE users SET shield_count = shield_count - 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
        return False


async def get_shield_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT shield_count FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0


async def set_shield_until(user_id: int, hours: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET shield_until = datetime('now', '+' || ? || ' hours') WHERE user_id = ?",
            (hours, user_id)
        )
        await db.commit()


async def is_shield_active(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT shield_until FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0]:
            try:
                shield_until = datetime.fromisoformat(row[0])
                return shield_until > datetime.now()
            except:
                pass
        return False


async def deactivate_shield(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET shield_until = NULL WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_streak(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT streak FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0


async def update_streak(user_id: int, new_streak: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT streak_record FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        current_record = row[0] if row else 0
        new_record = max(new_streak, current_record)
        
        await db.execute(
            "UPDATE users SET streak = ?, streak_record = ? WHERE user_id = ?",
            (new_streak, new_record, user_id)
        )
        await db.commit()
        return new_record


async def increment_streak(user_id: int) -> int:
    user = await get_user(user_id)
    if not user:
        return 0
    
    new_streak = user['streak'] + 1
    new_record = max(new_streak, user['streak_record'])
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET streak = ?, streak_record = ? WHERE user_id = ?",
            (new_streak, new_record, user_id)
        )
        await db.commit()
    return new_streak


async def increment_messages_today(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


async def reset_daily_messages():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET messages_today = 0, streak_awarded_today = 0")
        await db.commit()


async def get_top_streak(limit: int = 15) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT user_id, name, telegram_username, tg_name, streak, streak_record
            FROM users 
            WHERE streak > 0 AND is_banned = 0
            ORDER BY streak DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            data = dict(row)
            # Логика приоритета: 1. Кастомное имя по /name -> 2. Имя+Фамилия из TG -> 3. Юзернейм -> 4. ID
            if data.get('name'):
                data['display_name'] = data['name']
            else:
                data['display_name'] = data.get('tg_name') or data.get('telegram_username') or str(data['user_id'])
            result.append(data)
        return result


async def get_top_messages_today(limit: int = 15) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT user_id, name, telegram_username, tg_name, messages_today
            FROM users 
            WHERE messages_today > 0 AND is_banned = 0
            ORDER BY messages_today DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            data = dict(row)
            # Применяем аналогичную логику приоритета для топа по сообщениям
            if data.get('name'):
                data['display_name'] = data['name']
            else:
                data['display_name'] = data.get('tg_name') or data.get('telegram_username') or str(data['user_id'])
            result.append(data)
        return result


async def start_redemption(user_id: int, lost_streak: int):
    expires_at = datetime.now() + timedelta(hours=REDEMPTION_HOURS)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users 
            SET redemption_active = 1,
                redemption_target = ?,
                redemption_progress = 0,
                redemption_streak_to_restore = ?,
                redemption_expires_at = ?
            WHERE user_id = ?
        """, (REDEMPTION_TARGET, lost_streak, expires_at.isoformat(), user_id))
        await db.commit()


async def update_redemption_progress(user_id: int, increment: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users 
            SET redemption_progress = redemption_progress + ?
            WHERE user_id = ? AND redemption_active = 1
        """, (increment, user_id))
        await db.commit()


async def get_redemption_status(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT redemption_active, redemption_target, redemption_progress, 
                   redemption_streak_to_restore, redemption_expires_at
            FROM users 
            WHERE user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()
        if row:
            return {
                'active': row['redemption_active'] == 1,
                'target': row['redemption_target'] if row['redemption_target'] is not None else 200,
                'progress': row['redemption_progress'] if row['redemption_progress'] is not None else 0,
                'streak_to_restore': row['redemption_streak_to_restore'] if row['redemption_streak_to_restore'] is not None else 0,
                'expires_at': row['redemption_expires_at']
            }
        return None


async def complete_redemption(user_id: int):
    user = await get_user(user_id)
    if not user:
        return
    
    streak_to_restore = user.get('redemption_streak_to_restore', 0)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users 
            SET streak = ?,
                redemption_active = 0,
                redemption_progress = 0,
                redemption_target = 0,
                redemption_streak_to_restore = 0,
                redemption_expires_at = NULL
            WHERE user_id = ?
        """, (streak_to_restore, user_id))
        await db.commit()


async def fail_redemption(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users 
            SET redemption_active = 0,
                redemption_progress = 0,
                redemption_target = 0,
                redemption_streak_to_restore = 0,
                redemption_expires_at = NULL
            WHERE user_id = ?
        """, (user_id,))
        await db.commit()


async def check_expired_redemptions() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id FROM users 
            WHERE redemption_active = 1 
              AND redemption_expires_at < datetime('now')
        """)
        expired = await cursor.fetchall()
        
        for row in expired:
            await fail_redemption(row[0])
        
        return [row[0] for row in expired]


async def add_reward_history(user_id: int, reward_type: str, position: int, coins: int, streak: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO rewards_history (user_id, reward_type, position, coins, streak)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, reward_type, position, coins, streak))
        await db.commit()


async def award_daily_top() -> List[Dict]:
    top = await get_top_messages_today(3)
    rewards = [500, 250, 100]
    awarded = []
    
    for i, user in enumerate(top):
        if user['messages_today'] > 0:
            coins = rewards[i] if i < len(rewards) else 0
            await add_coins(user['user_id'], coins)
            await add_reward_history(user['user_id'], 'daily_top', i + 1, coins, user['messages_today'])
            awarded.append(user)
    
    return awarded


async def award_weekly_top() -> List[tuple]:
    top = await get_top_streak(3)
    rewards = [(1000, 1), (1000, 2), (1000, 3)]
    
    awarded = []
    for i, (coins, position) in enumerate(rewards):
        if i < len(top) and top[i]['streak'] > 0:
            user = top[i]
            await add_coins(user['user_id'], coins)
            await add_reward_history(user['user_id'], 'weekly_top', position, coins, user['streak'])
            awarded.append((user, position, coins))
    
    return awarded


async def get_inactive_users() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT user_id, name, telegram_username, last_activity, streak
            FROM users
            WHERE last_activity < datetime('now', '-24 hours')
              AND (shield_until IS NULL OR shield_until < datetime('now'))
              AND is_banned = 0
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def ban_user(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0] == 1:
            return False
        
        await db.execute(
            "UPDATE users SET is_banned = 1 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
        return True


async def pardon_user(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or row[0] == 0:
            return False
        
        await db.execute(
            "UPDATE users SET is_banned = 0 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
        return True


async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row and row[0] == 1


async def get_last_ping(user_id: int) -> Optional[datetime]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT last_ping FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0]:
            try:
                return datetime.fromisoformat(row[0])
            except:
                return None
        return None


async def update_last_ping(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_ping = datetime('now') WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


async def get_redemption_failed_notified(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT redemption_failed_notified FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row and row[0] == 1


async def set_redemption_failed_notified(user_id: int, value: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET redemption_failed_notified = ? WHERE user_id = ?",
            (value, user_id)
        )
        await db.commit()


async def reset_redemption_failed_notified(user_id: int):
    await set_redemption_failed_notified(user_id, 0)
