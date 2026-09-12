import json
import os
import time
from datetime import datetime, timedelta

import aiosqlite

from .config import DATABASE_PATH, CACHE_TTL


async def init_db():
    directory = os.path.dirname(DATABASE_PATH)

    if directory:
        os.makedirs(directory, exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                code TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_seen INTEGER NOT NULL
            )
        """)

        await db.commit()


async def add_query():
    today = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO daily_stats(date, count)
            VALUES (?, 1)
            ON CONFLICT(date)
            DO UPDATE SET count = count + 1
        """, (today,))

        await db.commit()


async def add_user(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO users(user_id, first_seen)
            VALUES (?, ?)
        """, (
            user_id,
            int(time.time()),
        ))

        await db.commit()


async def get_stats(days: int = 5):
    start_date = datetime.now() - timedelta(days=days)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            SELECT date, count
            FROM daily_stats
            WHERE date >= ?
            ORDER BY date ASC
        """, (
            start_date.strftime("%Y-%m-%d"),
        ))

        return await cursor.fetchall()


async def get_user_count():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users"
        )

        row = await cursor.fetchone()

    return row[0]


async def get_cache(code: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            SELECT data, updated_at
            FROM cache
            WHERE code = ?
        """, (code,))

        row = await cursor.fetchone()

    if not row:
        return None

    data, updated_at = row

    if int(time.time()) - updated_at > CACHE_TTL:
        return None

    try:
        return json.loads(data)
    except Exception:
        return None


async def set_cache(code: str, data: dict):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO cache(code, data, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(code)
            DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
        """, (
            code,
            json.dumps(data, ensure_ascii=False),
            int(time.time()),
        ))

        await db.commit()