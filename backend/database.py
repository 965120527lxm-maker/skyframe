"""
Database layer v2 — uploads + jobs tables
"""

import aiosqlite
from config import DB_PATH

CREATE_UPLOADS = """
CREATE TABLE IF NOT EXISTS uploads (
    id              TEXT PRIMARY KEY,
    user_id         TEXT,
    original_filename TEXT NOT NULL,
    storage_key     TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    file_size       INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'uploading',
    duration_sec    REAL,
    resolution      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
"""

CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    upload_id       TEXT NOT NULL REFERENCES uploads(id),
    model_name      TEXT NOT NULL,
    replicate_id    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    progress        REAL DEFAULT 0,
    output_key      TEXT,
    output_size     INTEGER,
    error_message   TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    FOREIGN KEY (upload_id) REFERENCES uploads(id)
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    await db.execute(CREATE_UPLOADS)
    await db.execute(CREATE_JOBS)
    await db.commit()
    await db.close()


# ── Uploads ────────────────────────────────────────────
async def insert_upload(record: dict):
    db = await get_db()
    await db.execute(
        """INSERT INTO uploads
           (id, user_id, original_filename, storage_key, mime_type, file_size, status, created_at)
           VALUES (:id, :user_id, :original_filename, :storage_key, :mime_type, :file_size, :status, :created_at)""",
        record,
    )
    await db.commit()
    await db.close()


async def update_upload(upload_id: str, fields: dict):
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = upload_id
    db = await get_db()
    await db.execute(f"UPDATE uploads SET {sets} WHERE id = :id", fields)
    await db.commit()
    await db.close()


async def get_upload(upload_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,))
    row = await cursor.fetchone()
    await db.close()
    return dict(row) if row else None


async def list_uploads(limit: int = 50, offset: int = 0) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM uploads ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


# ── Jobs ───────────────────────────────────────────────
async def insert_job(record: dict):
    db = await get_db()
    await db.execute(
        """INSERT INTO jobs
           (id, upload_id, model_name, status, created_at)
           VALUES (:id, :upload_id, :model_name, :status, :created_at)""",
        record,
    )
    await db.commit()
    await db.close()


async def update_job(job_id: str, fields: dict):
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = job_id
    db = await get_db()
    await db.execute(f"UPDATE jobs SET {sets} WHERE id = :id", fields)
    await db.commit()
    await db.close()


async def get_job(job_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = await cursor.fetchone()
    await db.close()
    return dict(row) if row else None


async def get_jobs_by_upload(upload_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM jobs WHERE upload_id = ? ORDER BY created_at DESC", (upload_id,)
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


async def get_pending_jobs() -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM jobs WHERE status IN ('pending', 'processing') ORDER BY created_at ASC"
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]
