import json
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiosqlite

from .config import DATABASE_PATH, MAGNET_CACHE_TTL, STATISTICS_TIMEZONE

_stats_timezone = ZoneInfo(STATISTICS_TIMEZONE)
_DB_TIMEOUT = 10


async def init_db():
    directory = os.path.dirname(DATABASE_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=10000")
        await db.execute("""CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS cache (
            code TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at INTEGER NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, first_seen INTEGER NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS query_cooldowns (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            last_query_at INTEGER NOT NULL, PRIMARY KEY (chat_id, user_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS upstream_request_times (
            requested_at REAL NOT NULL
        )""")
        await db.execute(
            "DELETE FROM query_cooldowns WHERE last_query_at < ?",
            (int(time.time()) - 86400,),
        )
        await db.commit()


async def add_query():
    today = datetime.now(_stats_timezone).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        await db.execute("""INSERT INTO daily_stats(date, count) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET count = count + 1""", (today,))
        await db.commit()


async def add_user(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        await db.execute("""INSERT OR IGNORE INTO users(user_id, first_seen)
            VALUES (?, ?)""", (user_id, int(time.time())))
        await db.commit()


async def acquire_query_cooldown(chat_id: int, user_id: int, cooldown: int) -> bool:
    """Atomically enforce a per-user, per-chat cooldown across processes."""
    now = int(time.time())
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            "SELECT last_query_at FROM query_cooldowns WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        row = await cursor.fetchone()
        if row and now - row[0] < cooldown:
            await db.rollback()
            return False
        await db.execute("""INSERT INTO query_cooldowns(chat_id, user_id, last_query_at)
            VALUES (?, ?, ?) ON CONFLICT(chat_id, user_id)
            DO UPDATE SET last_query_at = excluded.last_query_at""",
            (chat_id, user_id, now))
        await db.commit()
        return True


async def acquire_upstream_request_slot(limit: int, window_seconds: int = 60) -> float:
    """Return zero when admitted, otherwise seconds to wait; shared by all processes."""
    now = time.time()
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "DELETE FROM upstream_request_times WHERE requested_at <= ?",
            (now - window_seconds,),
        )
        cursor = await db.execute(
            "SELECT COUNT(*), MIN(requested_at) FROM upstream_request_times"
        )
        count, oldest = await cursor.fetchone()
        if count >= limit:
            await db.commit()
            return max(0.05, window_seconds - (now - oldest))
        await db.execute(
            "INSERT INTO upstream_request_times(requested_at) VALUES (?)", (now,)
        )
        await db.commit()
        return 0


async def get_stats(days: int = 5):
    if days < 1:
        raise ValueError("days must be at least 1")
    start_date = datetime.now(_stats_timezone).date() - timedelta(days=days - 1)
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        cursor = await db.execute("""SELECT date, count FROM daily_stats
            WHERE date >= ? ORDER BY date ASC""", (start_date.strftime("%Y-%m-%d"),))
        return await cursor.fetchall()


async def get_user_count():
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
    return row[0]


async def get_cache(code: str):
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        cursor = await db.execute(
            "SELECT data, updated_at FROM cache WHERE code = ?", (code,)
        )
        row = await cursor.fetchone()
    if not row:
        return None
    data, updated_at = row
    if int(time.time()) - updated_at > MAGNET_CACHE_TTL:
        async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
            await db.execute("DELETE FROM cache WHERE code = ?", (code,))
            await db.commit()
        return None
    try:
        return json.loads(data)
    except (TypeError, json.JSONDecodeError):
        return None


async def set_cache(code: str, data: dict):
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        await db.execute("""INSERT INTO cache(code, data, updated_at)
            VALUES (?, ?, ?) ON CONFLICT(code) DO UPDATE SET
            data = excluded.data, updated_at = excluded.updated_at""",
            (code, json.dumps(data, ensure_ascii=False), int(time.time())))
        await db.commit()


async def prune_cache():
    cutoff = int(time.time()) - MAGNET_CACHE_TTL
    async with aiosqlite.connect(DATABASE_PATH, timeout=_DB_TIMEOUT) as db:
        await db.execute("DELETE FROM cache WHERE updated_at < ?", (cutoff,))
        await db.commit()
