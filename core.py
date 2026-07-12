# core.py

import logging
import random
import json
import os
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from config import (
    RANKS, ACHIEVEMENT_DAYS, REDEMPTION_TARGET, REDEMPTION_HOURS,
    TRIGGER_SYMBOLS, MOOD_SYMBOLS, TRIGGER_NAMES, MOOD_NAMES,
    get_rank_by_streak, DB_PATH, PICS_PATH, CHAT_ID
)
from db import (
    get_user, register_user, update_last_activity, add_coins,
    get_streak, increment_streak, update_streak,
    increment_messages_today,
    get_shield_count, is_shield_active, use_shield, set_shield_until, deactivate_shield,
    start_redemption, update_redemption_progress, get_redemption_status,
    complete_redemption, fail_redemption,
    get_top_streak, get_top_messages_today,
    add_reward_history,
    add_shield,
    is_user_banned, ban_user,
    get_last_ping, update_last_ping,
    get_redemption_failed_notified, set_redemption_failed_notified, reset_redemption_failed_notified
)

logger = logging.getLogger(__name__)

PHRASES_FILE = "phrases.json"
_phrase_cache = {}
_last_rank_notified = {}
_achievement_sent = {}


def load_phrases():
    global _phrase_cache
    if not os.path.exists(PHRASES_FILE):
        with open(PHRASES_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
        _phrase_cache = {}
        return
    
    try:
        with open(PHRASES_FILE, 'r', encoding='utf-8') as f:
            _phrase_cache = json.load(f)
        logger.info(f"📚 Загружено фраз: {sum(len(v) for v in _phrase_cache.values())}")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фраз: {e}")
        _phrase_cache = {}


def save_phrases():
    try:
        with open(PHRASES_FILE, 'w', encoding='utf-8') as f:
            json.dump(_phrase_cache, f, ensure_ascii=False, indent=2)
        logger.info("💾 Фразы сохранены")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения фраз: {e}")
        return False


def get_random_phrase(trigger: str, mood: str = None) -> Optional[str]:
    phrases = _phrase_cache.get(trigger, [])
    if not phrases:
        return None
    
    if mood:
        filtered = [p for p in phrases if p.get('mood') == mood]
        if filtered:
            return random.choice(filtered)['text']
    
    return random.choice(phrases)['text']


def get_rank_phrase(rank_name: str) -> Optional[str]:
    phrases = _phrase_cache.get('RANK_UP', [])
    rank_phrases = [p for p in phrases if rank_name.lower() in p['text'].lower()]
    if rank_phrases:
        return random.choice(rank_phrases)['text']
    return None


def get_streak_achievement(day: int) -> Optional[str]:
    phrases = _phrase_cache.get('STREAK_ACHIEVEMENT', [])
    day_phrases = [p for p in phrases if str(day) in p['text']]
    if day_phrases:
        return random.choice(day_phrases)['text']
    return None


def parse_phrase(text: str) -> Optional[Dict]:
    if len(text) < 2:
        return None
    
    trigger_symbol = text[0]
    mood_symbol = text[1]
    
    if trigger_symbol not in TRIGGER_SYMBOLS:
        return None
    if mood_symbol not in MOOD_SYMBOLS:
        return None
    
    phrase_text = text[2:].strip()
    if len(phrase_text) < 3:
        return None
    
    return {
        'trigger': TRIGGER_SYMBOLS[trigger_symbol],
        'mood': MOOD_SYMBOLS[mood_symbol],
        'text': phrase_text
    }


def add_phrase_from_text(text: str) -> Tuple[bool, str, Optional[Dict]]:
    parsed = parse_phrase(text)
    if not parsed:
        return False, "❌ Неверный формат! Используй: !₽ Текст", None
    
    trigger = parsed['trigger']
    mood = parsed['mood']
    phrase_text = parsed['text']
    
    if trigger not in _phrase_cache:
        _phrase_cache[trigger] = []
    
    for p in _phrase_cache[trigger]:
        if p['text'].lower() == phrase_text.lower():
            return False, "⚠️ Такая фраза уже есть!", None
    
    _phrase_cache[trigger].append({'text': phrase_text, 'mood': mood})
    save_phrases()
    
    return True, "✅ Фраза добавлена!", parsed


def delete_phrase(trigger: str, text: str) -> bool:
    if trigger not in _phrase_cache:
        return False
    
    for i, p in enumerate(_phrase_cache[trigger]):
        if p['text'] == text:
            del _phrase_cache[trigger][i]
            save_phrases()
            return True
    return False


def get_all_phrases() -> List[Dict]:
    result = []
    for trigger, phrases in _phrase_cache.items():
        for p in phrases:
            result.append({
                'trigger': trigger,
                'mood': p.get('mood', 'SARCASTIC'),
                'text': p['text']
            })
    return result


def _get_files_in_folder(folder_path: str) -> List[str]:
    if not os.path.exists(folder_path):
        return []
    files = []
    for f in os.listdir(folder_path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            files.append(os.path.join(folder_path, f))
    return files


def _get_trigger_code(trigger: str) -> Optional[str]:
    codes = {
        'DAILY_GREETING': 'gre',
        'ONE_DAY_INACTIVE': 'ina',
        'MULTI_DAY_INACTIVE': 'mul',
        'MULTI_DAY_ULTRA': 'ult',
        'RETURN': 'ret',
        'RETURN_AGO': 'ago',
        'RANK_UP': 'ran',
        'STREAK_ACHIEVEMENT': 'str'
    }
    return codes.get(trigger)


def _get_mood_code(mood: str) -> Optional[str]:
    codes = {
        'SARCASTIC': 'sar',
        'ANGRY': 'ang',
        'FURIOUS': 'fur'
    }
    return codes.get(mood)


def get_default_mood_for_trigger(trigger: str) -> str:
    defaults = {
        'DAILY_GREETING': 'SARCASTIC',
        'ONE_DAY_INACTIVE': 'ANGRY',
        'MULTI_DAY_INACTIVE': 'FURIOUS',
        'MULTI_DAY_ULTRA': 'FURIOUS',
        'RETURN': 'SARCASTIC',
        'RETURN_AGO': 'SARCASTIC',
        'RANK_UP': 'SARCASTIC',
        'STREAK_ACHIEVEMENT': 'SARCASTIC'
    }
    return defaults.get(trigger, 'SARCASTIC')


def get_random_picture(trigger: str, mood: str = None) -> Optional[str]:
    trigger_code = _get_trigger_code(trigger)
    if not trigger_code:
        return None
    
    if not mood:
        mood = get_default_mood_for_trigger(trigger)
    
    mood_code = _get_mood_code(mood)
    if not mood_code:
        return None
    
    folder = f"{PICS_PATH}/{trigger_code}_{mood_code}"
    files = _get_files_in_folder(folder)
    if files:
        return random.choice(files)
    return None


async def process_user_message(user_id: int, chat_id: int, username: str = None, tg_name: str = None) -> Dict:
    global _last_rank_notified, _achievement_sent
    
    if await is_user_banned(user_id):
        return {'text': None}
    
    await register_user(user_id, username, tg_name)
    user = await get_user(user_id)
    
    is_main_chat = (chat_id == CHAT_ID)
    
    if is_main_chat:
        await update_last_activity(user_id)
        await increment_messages_today(user_id)
    
    response_data = {
        'text': None,
        'need_media': False,
        'trigger': None,
        'mood': None,
        'send_to_dm': False
    }
    
    if is_main_chat:
        redemption = await get_redemption_status(user_id)
        if redemption and redemption.get('active', False):
            await update_redemption_progress(user_id)
            progress = redemption['progress'] + 1
            target = redemption['target']
            
            if progress >= target:
                await complete_redemption(user_id)
                response_data['text'] = f"🎉 Ты восстановил стрик в {redemption['streak_to_restore']} дней! 🦊"
                response_data['send_to_dm'] = True
                return response_data
            elif progress % 50 == 0:
                remaining = target - progress
                response_data['text'] = f"📊 {progress}/{target} сообщений до восстановления. Осталось {remaining}!"
                response_data['send_to_dm'] = True
                return response_data
    
    last_activity = user.get('last_activity')
    return_trigger = None
    
    if last_activity and is_main_chat:
        try:
            last_time = datetime.fromisoformat(last_activity)
            seconds_since = (datetime.now() - last_time).total_seconds()
            
            if seconds_since >= 7 * 24 * 3600:
                return_trigger = 'RETURN_AGO'
            elif seconds_since >= 86400:
                return_trigger = 'RETURN'
        except:
            pass
    
    if last_activity and is_main_chat:
        try:
            last_time = datetime.fromisoformat(last_activity)
            hours_since = (datetime.now() - last_time).total_seconds()
            
            if hours_since >= 24 * 3600:
                if await is_shield_active(user_id):
                    await deactivate_shield(user_id)
                    response_data['text'] = "🛡️ Щит спас стрик! Но он сгорел. Купи новый в /shop."
                    response_data['send_to_dm'] = True
                    return response_data
                else:
                    old_streak = user['streak']
                    await update_streak(user_id, 0)
                    await start_redemption(user_id, old_streak)
                    await reset_redemption_failed_notified(user_id)
                    response_data['text'] = (
                        f"💔 Стрик в {old_streak} дней сброшен.\n\n"
                        f"🔄 **Шанс восстановить!**\n"
                        f"Напиши **{REDEMPTION_TARGET} сообщений** за {REDEMPTION_HOURS} часов!\n\n"
                        f"Прогресс: **/redemption**"
                    )
                    response_data['send_to_dm'] = True
                    return response_data
        except:
            pass
    
    should_increment = False
    
    if is_main_chat:
        messages_today = user.get('messages_today', 0)
        streak_awarded_today = user.get('streak_awarded_today', 0)
        
        if last_activity and streak_awarded_today == 0 and messages_today >= 100:
            should_increment = True
        
        if should_increment:
            new_streak = await increment_streak(user_id)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET streak_awarded_today = 1 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
        else:
            new_streak = user['streak']
        
        rank = get_rank_by_streak(new_streak)
        await add_coins(user_id, rank['income'])
    else:
        new_streak = user['streak']
    
    current_rank = user.get('rank', 'Без ранга')
    new_rank = get_rank_by_streak(new_streak)
    
    if new_rank['name'] != current_rank and new_rank['name'] != 'Без ранга' and is_main_chat:
        last_notified = _last_rank_notified.get(user_id)
        if last_notified != new_rank['name']:
            _last_rank_notified[user_id] = new_rank['name']
            
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (new_rank['name'], user_id))
                await db.commit()
            
            phrase = get_rank_phrase(new_rank['name'])
            if phrase:
                response_data['text'] = f"🏆 Поздравляю! Ты достиг ранга {new_rank['name']}!\n\n{phrase}"
            else:
                response_data['text'] = f"🏆 Поздравляю! Ты достиг ранга {new_rank['name']}!"
            response_data['send_to_dm'] = True
            response_data['need_media'] = True
            response_data['trigger'] = 'RANK_UP'
            response_data['mood'] = 'SARCASTIC'
            return response_data
    
    if new_streak in ACHIEVEMENT_DAYS and is_main_chat:
        if _achievement_sent.get(user_id) != new_streak:
            _achievement_sent[user_id] = new_streak
            phrase = get_streak_achievement(new_streak)
            if phrase:
                response_data['text'] = f"🎉 {new_streak} дней стрика!\n\n{phrase}"
            else:
                response_data['text'] = f"🎉 Ты достиг {new_streak} дней стрика! 🦊"
            response_data['send_to_dm'] = True
            response_data['need_media'] = True
            response_data['trigger'] = 'STREAK_ACHIEVEMENT'
            response_data['mood'] = 'SARCASTIC'
            return response_data
    
    if should_increment and is_main_chat:
        if return_trigger:
            phrase = get_random_phrase(return_trigger, 'SARCASTIC')
        else:
            phrase = get_random_phrase('DAILY_GREETING', 'SARCASTIC')
        
        if phrase:
            response_data['text'] = phrase
            response_data['need_media'] = True
            response_data['trigger'] = return_trigger or 'DAILY_GREETING'
            response_data['mood'] = 'SARCASTIC'
            return response_data
    
    return response_data


async def check_inactive_users() -> List[Dict]:
    from db import get_inactive_users
    
    inactive = await get_inactive_users()
    result = []
    now = datetime.now()
    
    for user in inactive:
        if not user.get('last_activity'):
            continue
        
        if await is_user_banned(user['user_id']):
            continue
        
        last_time = datetime.fromisoformat(user['last_activity'])
        seconds_since = (now - last_time).total_seconds()
        
        if seconds_since >= 30 * 24 * 3600:
            if not await is_user_banned(user['user_id']):
                await ban_user(user['user_id'])
                logger.info(f"🚫 Автобан: {user['user_id']} за месяц неактива")
            continue
        
        h24 = 24 * 3600
        h48 = 48 * 3600
        h_ultra = 7 * 24 * 3600
        h3 = 3 * 3600
        
        if seconds_since >= h24:
            last_ping = await get_last_ping(user['user_id'])
            
            if not last_ping or (now - last_ping).total_seconds() >= h3:
                if seconds_since >= h_ultra:
                    trigger = 'MULTI_DAY_ULTRA'
                elif seconds_since >= h48:
                    trigger = 'MULTI_DAY_INACTIVE'
                else:
                    trigger = 'ONE_DAY_INACTIVE'
                
                await update_last_ping(user['user_id'])
                
                result.append({
                    'user': user,
                    'trigger': trigger,
                    'mood': 'FURIOUS'
                })
    
    return result


async def get_user_profile(user_id: int) -> Optional[str]:
    user = await get_user(user_id)
    if not user:
        return None
    
    shield_count = await get_shield_count(user_id)
    shield_active = await is_shield_active(user_id)
    
    redemption = await get_redemption_status(user_id)
    redemption_text = ""
    if redemption and redemption.get('active', False):
        progress = redemption.get('progress', 0)
        target = redemption.get('target', 200)
        redemption_text = f"\n🔄 Искупление: {progress}/{target} сообщений"
    
    shield_status = "🟢 Активен" if shield_active else "🔴 Не активен"
    messages_today = user.get('messages_today', 0)
    
    text = (
        f"📋 **Профиль**\n"
        f"| Имя: {user['name'] or 'Без имени'}\n"
        f"| Ранг: {user['rank']}\n"
        f"| Стрик: {user['streak']} дней\n"
        f"| Рекорд: {user['streak_record']} дней\n"
        f"| Сообщений сегодня: {messages_today}\n"
        f"| Монеты: {user['coins']:.1f}\n"
        f"| Щитов: {shield_count} шт.\n"
        f"| Щит: {shield_status}{redemption_text}"
    )
    return text


async def buy_shield(user_id: int) -> Tuple[bool, str]:
    user = await get_user(user_id)
    if not user:
        return False, "❌ Ты не зарегистрирован!"
    
    if user['coins'] < 100:
        return False, f"❌ Недостаточно монет! Нужно 100, у тебя {user['coins']:.1f}"
    
    await add_coins(user_id, -100)
    await add_shield(user_id, 1)
    shield_count = await get_shield_count(user_id)
    return True, f"✅ Щит куплен! Теперь у тебя {shield_count} щитов."


async def activate_shield(user_id: int) -> Tuple[bool, str]:
    shield_count = await get_shield_count(user_id)
    if shield_count == 0:
        return False, "❌ У тебя нет щитов! Купи в /shop."
    
    if await is_shield_active(user_id):
        return False, "⏳ У тебя уже активен щит!"
    
    await use_shield(user_id)
    await set_shield_until(user_id, 36)
    shield_count = await get_shield_count(user_id)
    return True, f"⚡ Щит активирован на 36 часов! Осталось щитов: {shield_count}"


async def get_top_streak_text(limit: int = 15) -> str:
    top = await get_top_streak(limit)
    if not top:
        return "📊 Пока нет данных. Напиши что-нибудь!"
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    text = "🏆 ТОП СТРИКОВ\n\n"
    
    for i, user in enumerate(top):
        medal = medals[i] if i < 10 else f"{i+1}."
        name = user['display_name']
        text += f"{medal} {name} — {user['streak']} дней\n"
    
    text += "\n✨ Награды в воскресенье:\n🥇 1000 | 🥈 1000 | 🥉 1000 монет"
    return text


async def get_top_messages_text(limit: int = 15) -> str:
    top = await get_top_messages_today(limit)
    if not top:
        return "📊 Сегодня пока никто не писал. Будь первым!"
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    text = "💬 ТОП СООБЩЕНИЙ (за сегодня)\n\n"
    
    for i, user in enumerate(top):
        medal = medals[i] if i < 10 else f"{i+1}."
        name = user['display_name']
        text += f"{medal} {name} — {user['messages_today']} сообщений\n"
    
    text += "\n✨ Награды:\n🥇 500 | 🥈 250 | 🥉 100 монет"
    return text


async def handle_inactive_user(user_id: int, trigger: str, mood: str) -> Dict:
    user = await get_user(user_id)
    if not user:
        return {'text': None, 'send_to_dm': True}
    
    if await is_user_banned(user_id):
        return {'text': None, 'send_to_dm': True}
    
    if await is_shield_active(user_id):
        await deactivate_shield(user_id)
        return {
            'text': "🛡️ Щит спас стрик! Но он сгорел. Купи новый в /shop.",
            'chat_id': user_id,
            'send_to_dm': True
        }
    
    last_activity = user.get('last_activity')
    seconds_since = 0
    if last_activity:
        try:
            last_time = datetime.fromisoformat(last_activity)
            seconds_since = (datetime.now() - last_time).total_seconds()
        except:
            pass
    
    h48 = 48 * 3600
    
    redemption = await get_redemption_status(user_id)
    is_already_redeeming = redemption and redemption.get('active', False)
    
    text = ""
    
    if not is_already_redeeming:
        old_streak = user['streak']
        await update_streak(user_id, 0)
        await start_redemption(user_id, old_streak)
        await reset_redemption_failed_notified(user_id)
        text = f"💔 Стрик в {old_streak} дней сброшен.\n\n"
    
    phrase = get_random_phrase(trigger, mood)
    if phrase:
        text += phrase
    else:
        if trigger == 'MULTI_DAY_INACTIVE' or trigger == 'MULTI_DAY_ULTRA':
            text += "😡 Ты пропал на несколько дней! Твой стрик на нуле, а ты всё молчишь!"
        else:
            text += "😠 Почему молчим? Возвращайся в чат!"
    
    if seconds_since >= h48:
        if not await get_redemption_failed_notified(user_id):
            text += "\n\n💀 Время на восстановление вышло. Стрик не восстановлен."
            await set_redemption_failed_notified(user_id, 1)
    else:
        if is_already_redeeming:
            progress = redemption.get('progress', 0) if redemption else 0
            target = redemption.get('target', 200) if redemption else 200
            remaining = target - progress
            text += f"\n\n🔄 **Шанс восстановить стрик!**\nНапиши **{remaining}** сообщений из {target}!\n\nПрогресс: **/redemption**"
    
    return {
        'text': text.strip(),
        'chat_id': user_id,
        'trigger': trigger,
        'mood': mood,
        'send_to_dm': True
    }


async def admin_give_coins(admin_id: int, identifier: str, amount: float) -> Tuple[bool, str]:
    from config import is_admin
    if not is_admin(admin_id):
        return False, "❌ Ты не админ!"
    
    from db import get_user_by_identifier
    user = await get_user_by_identifier(identifier)
    if not user:
        return False, f"❌ Пользователь '{identifier}' не найден."
    
    await add_coins(user['user_id'], amount)
    name = user.get('name') or user.get('tg_name') or user.get('telegram_username') or identifier
    return True, f"✅ {amount} коинов выдано {name} (ID: {user['user_id']})"


async def admin_set_shield(admin_id: int, identifier: str, hours: int) -> Tuple[bool, str]:
    from config import is_admin
    if not is_admin(admin_id):
        return False, "❌ Ты не админ!"
    
    from db import get_user_by_identifier
    user = await get_user_by_identifier(identifier)
    if not user:
        return False, f"❌ Пользователь '{identifier}' не найден."
    
    await set_shield_until(user['user_id'], hours)
    name = user.get('name') or user.get('tg_name') or user.get('telegram_username') or identifier
    return True, f"✅ Щит на {hours} часов выдан {name} (ID: {user['user_id']})"


async def admin_set_rank(admin_id: int, identifier: str, rank_name: str) -> Tuple[bool, str]:
    from config import is_admin, RANKS
    if not is_admin(admin_id):
        return False, "❌ Ты не админ!"
    
    valid_ranks = [r['name'] for r in RANKS]
    if rank_name not in valid_ranks:
        return False, f"❌ Неверный ранг. Доступны: {', '.join(valid_ranks)}"
    
    from db import get_user_by_identifier
    user = await get_user_by_identifier(identifier)
    if not user:
        return False, f"❌ Пользователь '{identifier}' не найден."
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank_name, user['user_id']))
        await db.commit()
    
    name = user.get('name') or user.get('tg_name') or user.get('telegram_username') or identifier
    return True, f"✅ Ранг '{rank_name}' установлен для {name} (ID: {user['user_id']})"


__all__ = [
    'load_phrases',
    'save_phrases',
    'get_random_phrase',
    'get_rank_phrase',
    'get_streak_achievement',
    'parse_phrase',
    'add_phrase_from_text',
    'delete_phrase',
    'get_all_phrases',
    'get_random_picture',
    'process_user_message',
    'check_inactive_users',
    'handle_inactive_user',
    'get_user_profile',
    'buy_shield',
    'activate_shield',
    'get_top_streak_text',
    'get_top_messages_text',
    'admin_give_coins',
    'admin_set_shield',
    'admin_set_rank'
]
