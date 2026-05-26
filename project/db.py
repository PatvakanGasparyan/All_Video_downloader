import os

import aiomysql

pool = None


def _db_config():
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", "5555"),
        "db": os.getenv("MYSQL_DATABASE", "downloader_db"),
    }


async def init_db():
    global pool
    cfg = _db_config()
    pool = await aiomysql.create_pool(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        db=cfg["db"],
        autocommit=True,
    )
    await _ensure_schema()


async def _ensure_schema():
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'videos'
                  AND COLUMN_NAME = 'quality'
                """
            )
            if not await cur.fetchone():
                await cur.execute(
                    "ALTER TABLE videos ADD COLUMN quality VARCHAR(16) NULL"
                )


async def close_pool():
    global pool
    if pool is not None:
        pool.close()
        await pool.wait_closed()
        pool = None


async def save_video(v):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO videos (title, original_url, filename, duration, filesize, quality) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    v["title"],
                    v["original_url"],
                    v["filename"],
                    v["duration"],
                    v["filesize"],
                    v.get("quality"),
                ),
            )
            return cur.lastrowid


async def get_videos():
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM videos ORDER BY created_at DESC")
            return await cur.fetchall()


async def delete_video(video_id):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT filename FROM videos WHERE id = %s", (video_id,))
            row = await cur.fetchone()
            if row:
                await cur.execute("DELETE FROM videos WHERE id = %s", (video_id,))
                return row[0]
