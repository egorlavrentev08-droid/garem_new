# core.py - ВСЯ БИЗНЕС-ЛОГИКА

import logging
import random
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from config import (
    RANKS, ACHIEVEMENT_DAYS, REDEMPTION_TARGET, REDEMPTION_HOURS,
    INACTIVE_FIRST_HOURS, INACTIVE_REPEAT_MIN, INACTIVE_REPEAT_MAX,
    TRIGGER_SYMBOLS, MOOD_SYMBOLS, TRIGGER_NAMES, MOOD_NAMES,
    get_rank_by_streak
)
from db import (
    get_user, register_user, update_last_activity, add_coins,
    get_streak, increment_streak, update_streak,
    increment_messages_today,
    get_shield_count, is_shield_active, use_shield, set_shield_until, deactivate_shield,
    start_redemption, update_redemption_progress, get_redemption_status,
    complete_redemption, fail_redemption,
    get_top_streak, get_top_messages_today,
    add_reward_history
)

logger = logging.getLogger(__name__)

# ============================================================
# 1. ФРАЗЫ (ИЗ JSON)
# ============================================================

PHRASES_FILE = "phrases.json"
_phrase_cache = {}


def load_phrases():
    """Загружает фразы из JSON"""
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
    """Сохраняет фразы в JSON"""
    try:
        with open(PHRASES_FILE, 'w', encoding='utf-8') as f:
            json.dump(_phrase_cache, f, ensure_ascii=False, indent=2)
        logger.info("💾 Фразы сохранены")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения фраз: {e}")
        return False


def get_random_phrase(trigger: str, mood: str = None) -> Optional[str]:
    """Возвращает случайную фразу для триггера и настроения"""
    phrases = _phrase_cache.get(trigger, [])
    if not phrases:
        return None
    
    if mood:
        filtered = [p for p in phrases if p.get('mood') == mood]
        if filtered:
            return random.choice(filtered)['text']
    
    return random.choice(phrases)['text']


def get_rank_phrase(rank_name: str) -> Optional[str]:
    """Возвращает фразу для повышения ранга"""
    phrases = _phrase_cache.get('RANK_UP', [])
    rank_phrases = [p for p in phrases if rank_name.lower() in p['text'].lower()]
    if rank_phrases:
        return random.choice(rank_phrases)['text']
    return None


def get_streak_achievement(day: int) -> Optional[str]:
    """Возвращает фразу для достижения стрика"""
    phrases = _phrase_cache.get('STREAK_ACHIEVEMENT', [])
    day_phrases = [p for p in phrases if str(day) in p['text']]
    if day_phrases:
        return random.choice(day_phrases)['text']
    return None


def parse_phrase(text: str) -> Optional[Dict]:
    """Парсит сообщение формата: !₽ Текст фразы"""
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
    """Добавляет фразу из строки с символами"""
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
    """Удаляет фразу"""
    if trigger not in _phrase_cache:
        return False
    
    for i, p in enumerate(_phrase_cache[trigger]):
        if p['text'] == text:
            del _phrase_cache[trigger][i]
            save_phrases()
            return True
    return False


def get_all_phrases() -> List[Dict]:
    """Возвращает все фразы"""
    result = []
    for trigger, phrases in _phrase_cache.items():
        for p in phrases:
            result.append({
                'trigger': trigger,
                'mood': p.get('mood', 'SARCASTIC'),
                'text': p['text']
            })
    return result


# ============================================================
# 2. МЕДИА (КАРТИНКИ И МЕМЫ)
# ============================================================

from config import MEDIA_BASE_PATH, PICS_PATH, MEMS_PATH

def _get_files_in_folder(folder_path: str) -> List[str]:
    """Возвращает список файлов в папке"""
    if not os.path.exists(folder_path):
        return []
    
    files = []
    for f in os.listdir(folder_path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            files.append(os.path.join(folder_path, f))
    return files


def get_random_picture(trigger: str, mood: str = None) -> Optional[str]:
    """Возвращает путь к случайной картинке"""
    trigger_code = {
        'DAILY_GREETING': 'gre',
        'ONE_DAY_INACTIVE': 'ina',
        'MULTI_DAY_INACTIVE': 'mul',
        'RETURN': 'ret',
        'RANK_UP': 'ran',
        'STREAK_ACHIEVEMENT': 'str'
    }.get(trigger)
    
    if not trigger_code:
        return None
    
    mood_code = {
        'SARCASTIC': 'sar',
        'ANGRY': 'ang',
        'FURIOUS': 'fur'
    }.get(mood) if mood else None
    
    # Ищем в pics
    base = PICS_PATH
    if not os.path.exists(base):
        return None
    
    all_files = []
    for folder in os.listdir(base):
        if not folder.startswith(f"{trigger_code}_"):
            continue
        if mood_code and not folder.endswith(f"_{mood_code}"):
            continue
        folder_path = os.path.join(base, folder)
        all_files.extend(_get_files_in_folder(folder_path))
    
    if all_files:
        return random.choice(all_files)
    return None


def get_random_meme(trigger: str, mood: str = None) -> Optional[str]:
    """Возвращает путь к случайному мему"""
    trigger_code = {
        'DAILY_GREETING': 'gre',
        'ONE_DAY_INACTIVE': 'ina',
        'MULTI_DAY_INACTIVE': 'mul',
        'RETURN': 'ret',
        'RANK_UP': 'ran',
        'STREAK_ACHIEVEMENT': 'str'
    }.get(trigger)
    
    if not trigger_code:
        return None
    
    mood_code = {
        'SARCASTIC': 'sar',
        'ANGRY': 'ang',
        'FURIOUS': 'fur'
    }.get(mood) if mood else None
    
    base = MEMS_PATH
    if not os.path.exists(base):
        return None
    
    all_files = []
    for folder in os.listdir(base):
        if not folder.startswith(f"{trigger_code}_"):
            continue
        if mood_code and not folder.endswith(f"_{mood_code}_mem"):
            continue
        folder_path = os.path.join(base, folder)
        all_files.extend(_get_files_in_folder(folder_path))
    
    if all_files:
        return random.choice(all_files)
    return None


def create_media_folders():
    """Создаёт все папки для медиа"""
    triggers = ['gre', 'ina', 'mul', 'ret', 'ran', 'str']
    moods = ['sar', 'ang', 'fur']
    
    for folder_type in ['pics', 'mems']:
        base = f"{MEDIA_BASE_PATH}/{folder_type}"
        os.makedirs(base, exist_ok=True)
        
        for trigger in triggers:
            for mood in moods:
                suffix = '_mem' if folder_type == 'mems' else ''
                folder = f"{base}/{trigger}_{mood}{suffix}"
                os.makedirs(folder, exist_ok=True)
    
    logger.info("✅ Папки для медиа созданы")


# ============================================================
# 3. ОСНОВНАЯ ЛОГИКА
# ============================================================

async def process_user_message(user_id: int, chat_id: int) -> Dict:
    """
    Обрабатывает сообщение пользователя.
    Возвращает словарь с данными для ответа.
    """
    # 1. Регистрация (если нет)
    user = await get_user(user_id)
    if not user:
        await register_user(user_id)
        user = await get_user(user_id)
    
    # 2. Обновляем активность
    await update_last_activity(user_id)
    await increment_messages_today(user_id)
    
    # 3. Проверяем стрик
    last_activity = user.get('last_activity')
    response_data = {
        'text': None,
        'picture': None,
        'meme': None,
        'need_media': False
    }
    
    # Проверяем искупление
    redemption = await get_redemption_status(user_id)
    if redemption and redemption['active']:
        await update_redemption_progress(user_id)
        progress = redemption['progress'] + 1
        target = redemption['target']
        
        if progress >= target:
            await complete_redemption(user_id)
            response_data['text'] = f"🎉 Ты восстановил стрик в {redemption['streak_to_restore']} дней! 🦊"
            return response_data
        elif progress % 50 == 0:
            remaining = target - progress
            response_data['text'] = f"📊 {progress}/{target} сообщений до восстановления. Осталось {remaining}!"
            return response_data
    
    # Проверяем стрик
    if last_activity:
        try:
            last_time = datetime.fromisoformat(last_activity)
            hours_since = (datetime.now() - last_time).total_seconds() / 3600
            
            if hours_since >= 24:
                # Проверяем щит
                if await is_shield_active(user_id):
                    await deactivate_shield(user_id)
                    response_data['text'] = "🛡️ Щит спас стрик! Но он сгорел. Купи новый в /shop."
                    return response_data
                else:
                    # Сбрасываем стрик
                    old_streak = user['streak']
                    await update_streak(user_id, 0)
                    await start_redemption(user_id, old_streak)
                    response_data['text'] = (
                        f"💔 Стрик в {old_streak} дней сброшен.\n\n"
                        f"🔄 **Шанс восстановить!**\n"
                        f"Напиши **{REDEMPTION_TARGET} сообщений** за {REDEMPTION_HOURS} часов!\n\n"
                        f"Прогресс: **/redemption**"
                    )
                    return response_data
        except:
            pass
    
    # Увеличиваем стрик (если не было пропуска)
    new_streak = await increment_streak(user_id)
    
    # 4. Начисляем монеты
    rank = get_rank_by_streak(new_streak)
    income = rank['income']
    await add_coins(user_id, income)
    
    # 5. Проверяем ранг
    current_rank = user.get('rank', 'Без ранга')
    if rank['name'] != current_rank and rank['name'] != 'Без ранга':
        # Обновляем ранг в БД
        async with aiosqlite.connect("dori.db") as db:
            await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank['name'], user_id))
            await db.commit()
        
        # Отправляем поздравление
        phrase = get_rank_phrase(rank['name'])
        if phrase:
            response_data['text'] = f"🏆 Поздравляю! Ты достиг ранга {rank['name']}!\n\n{phrase}"
        else:
            response_data['text'] = f"🏆 Поздравляю! Ты достиг ранга {rank['name']}!"
        response_data['need_media'] = True
        response_data['trigger'] = 'RANK_UP'
        response_data['mood'] = 'SARCASTIC'
        return response_data
    
    # 6. Проверяем достижения
    if new_streak in ACHIEVEMENT_DAYS:
        phrase = get_streak_achievement(new_streak)
        if phrase:
            response_data['text'] = f"🎉 {new_streak} дней стрика!\n\n{phrase}"
        else:
            response_data['text'] = f"🎉 Ты достиг {new_streak} дней стрика! 🦊"
        response_data['need_media'] = True
        response_data['trigger'] = 'STREAK_ACHIEVEMENT'
        response_data['mood'] = 'SARCASTIC'
        return response_data
    
    # 7. Ежедневное приветствие (если первый раз за день)
    if last_activity:
        try:
            last_time = datetime.fromisoformat(last_activity)
            if last_time.date() < datetime.now().date():
                phrase = get_random_phrase('DAILY_GREETING', 'SARCASTIC')
                if phrase:
                    response_data['text'] = phrase
                    response_data['need_media'] = True
                    response_data['trigger'] = 'DAILY_GREETING'
                    response_data['mood'] = 'SARCASTIC'
                    return response_data
        except:
            pass
    
    # 8. Обычный ответ (ничего особенного)
    # 80% фраза+картинка, 20% мем
    if random.random() < 0.8:
        phrase = get_random_phrase('DAILY_GREETING', 'SARCASTIC')
        if phrase:
            response_data['text'] = phrase
        response_data['need_media'] = True
        response_data['trigger'] = 'DAILY_GREETING'
        response_data['mood'] = 'SARCASTIC'
    else:
        response_data['need_media'] = True
        response_data['trigger'] = 'DAILY_GREETING'
        response_data['mood'] = 'SARCASTIC'
        response_data['is_meme'] = True
    
    return response_data


# ============================================================
# 4. ПРОВЕРКА НЕАКТИВА
# ============================================================

async def check_inactive_users() -> List[Dict]:
    """
    Проверяет неактивных пользователей и возвращает список тех,
    кому нужно отправить уведомление.
    """
    from db import get_inactive_users
    
    inactive = await get_inactive_users()
    result = []
    
    for user in inactive:
        if not user.get('last_activity'):
            continue
        
        hours_since = (datetime.now() - datetime.fromisoformat(user['last_activity'])).total_seconds() / 3600
        
        # Первое уведомление через 24 часа
        if 24 <= hours_since < 25:
            result.append({
                'user': user,
                'type': 'first',
                'trigger': 'ONE_DAY_INACTIVE',
                'mood': 'ANGRY'
            })
        # Повторные через 2-3 часа
        elif hours_since >= 25:
            # Проверяем, не отправляли ли недавно
            # Для простоты отправляем всегда (в scheduler будет ограничение)
            if hours_since % random.randint(2, 3) < 0.1:  # Примерная логика
                result.append({
                    'user': user,
                    'type': 'repeat',
                    'trigger': 'MULTI_DAY_INACTIVE' if hours_since >= 72 else 'ONE_DAY_INACTIVE',
                    'mood': 'FURIOUS' if hours_since >= 72 else 'ANGRY'
                })
    
    return result


# ============================================================
# 5. ПРОФИЛЬ
# ============================================================

async def get_user_profile(user_id: int) -> Optional[str]:
    """Возвращает текст профиля"""
    user = await get_user(user_id)
    if not user:
        return None
    
    shield_count = await get_shield_count(user_id)
    shield_active = await is_shield_active(user_id)
    
    redemption = await get_redemption_status(user_id)
    redemption_text = ""
    if redemption and redemption['active']:
        progress = redemption['progress']
        target = redemption['target']
        redemption_text = f"\n🔄 Искупление: {progress}/{target} сообщений"
    
    shield_status = "🟢 Активен" if shield_active else "🔴 Не активен"
    
    text = (
        f"📋 **Профиль**\n"
        f"| Имя: {user['name'] or 'Без имени'}\n"
        f"| Ранг: {user['rank']}\n"
        f"| Стрик: {user['streak']} дней\n"
        f"| Рекорд: {user['streak_record']} дней\n"
        f"| Монеты: {user['coins']:.1f}\n"
        f"| Щитов: {shield_count} шт.\n"
        f"| Щит: {shield_status}{redemption_text}"
    )
    return text


# ============================================================
# 6. МАГАЗИН
# ============================================================

async def buy_shield(user_id: int) -> Tuple[bool, str]:
    """Покупает щит за 100 монет"""
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
    """Активирует щит на 36 часов"""
    shield_count = await get_shield_count(user_id)
    if shield_count == 0:
        return False, "❌ У тебя нет щитов! Купи в /shop."
    
    if await is_shield_active(user_id):
        return False, "⏳ У тебя уже активен щит!"
    
    await use_shield(user_id)
    await set_shield_until(user_id, 36)
    
    shield_count = await get_shield_count(user_id)
    return True, f"⚡ Щит активирован на 36 часов! Осталось щитов: {shield_count}"


# ============================================================
# 7. ТОПЫ (ДЛЯ КОМАНД)
# ============================================================

async def get_top_streak_text(limit: int = 15) -> str:
    """Возвращает текст топа стриков"""
    top = await get_top_streak(limit)
    if not top:
        return "📊 Пока нет данных. Напиши что-нибудь!"
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    text = "🏆 **ТОП СТРИКОВ**\n\n"
    
    for i, user in enumerate(top):
        medal = medals[i] if i < 10 else f"{i+1}."
        name = user.get('name', user.get('telegram_username', 'Без имени'))
        text += f"{medal} **{name}** — {user['streak']} дней\n"
    
    text += "\n✨ **Награды в воскресенье:**\n🥇 1000 | 🥈 1000 | 🥉 1000 монет"
    return text


async def get_top_messages_text(limit: int = 15) -> str:
    """Возвращает текст топа сообщений за сегодня"""
    top = await get_top_messages_today(limit)
    if not top:
        return "📊 Сегодня пока никто не писал. Будь первым!"
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    text = "💬 **ТОП СООБЩЕНИЙ** (за сегодня)\n\n"
    
    for i, user in enumerate(top):
        medal = medals[i] if i < 10 else f"{i+1}."
        name = user.get('name', user.get('telegram_username', 'Без имени'))
        text += f"{medal} **{name}** — {user['messages_today']} сообщений\n"
    
    text += "\n✨ **1 место** получит 100 монет в 00:00 МСК!"
    return text


# ============================================================
# 8. ВСПОМОГАТЕЛЬНОЕ ДЛЯ SCHEDULER
# ============================================================

async def handle_inactive_user(user_id: int, trigger: str, mood: str) -> Dict:
    """
    Обрабатывает неактивного пользователя.
    Возвращает данные для отправки.
    """
    user = await get_user(user_id)
    if not user:
        return {'text': None}
    
    # Если щит активен — снимаем
    if await is_shield_active(user_id):
        await deactivate_shield(user_id)
        return {
            'text': "🛡️ Щит спас стрик! Но он сгорел. Купи новый в /shop.",
            'chat_id': user_id
        }
    
    # Проверяем, не активировано ли уже искупление
    redemption = await get_redemption_status(user_id)
    if redemption and redemption['active']:
        return {'text': None}
    
    # Сбрасываем стрик
    old_streak = user['streak']
    await update_streak(user_id, 0)
    await start_redemption(user_id, old_streak)
    
    # Готовим сообщение
    phrase = get_random_phrase(trigger, mood)
    text = phrase or f"💔 Стрик в {old_streak} дней сброшен."
    
    if trigger == 'MULTI_DAY_INACTIVE' and not phrase:
        text = f"😡 Ты пропал на несколько дней! Стрик в {old_streak} дней сброшен."
    
    text += f"\n\n🔄 **Шанс восстановить!**\nНапиши **{REDEMPTION_TARGET} сообщений** за {REDEMPTION_HOURS} часов!\n\nПрогресс: **/redemption**"
    
    return {
        'text': text,
        'chat_id': user_id,
        'trigger': trigger,
        'mood': mood
    }


# ============================================================
# 9. АДМИН-ФУНКЦИИ
# ============================================================

async def admin_give_coins(admin_id: int, identifier: str, amount: float) -> Tuple[bool, str]:
    """Выдаёт коины пользователю (только админ)"""
    from config import is_admin
    if not is_admin(admin_id):
        return False, "❌ Ты не админ!"
    
    from db import get_user_by_identifier
    user = await get_user_by_identifier(identifier)
    if not user:
        return False, f"❌ Пользователь '{identifier}' не найден."
    
    await add_coins(user['user_id'], amount)
    name = user.get('name', user.get('telegram_username', identifier))
    return True, f"✅ {amount} коинов выдано {name} (ID: {user['user_id']})"


async def admin_set_shield(admin_id: int, identifier: str, hours: int) -> Tuple[bool, str]:
    """Выдаёт щит пользователю (только админ)"""
    from config import is_admin
    if not is_admin(admin_id):
        return False, "❌ Ты не админ!"
    
    from db import get_user_by_identifier
    user = await get_user_by_identifier(identifier)
    if not user:
        return False, f"❌ Пользователь '{identifier}' не найден."
    
    await set_shield_until(user['user_id'], hours)
    name = user.get('name', user.get('telegram_username', identifier))
    return True, f"✅ Щит на {hours} часов выдан {name} (ID: {user['user_id']})"


async def admin_set_rank(admin_id: int, identifier: str, rank_name: str) -> Tuple[bool, str]:
    """Меняет ранг пользователю (только админ)"""
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
    
    async with aiosqlite.connect("dori.db") as db:
        await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank_name, user['user_id']))
        await db.commit()
    
    name = user.get('name', user.get('telegram_username', identifier))
    return True, f"✅ Ранг '{rank_name}' установлен для {name} (ID: {user['user_id']})"
