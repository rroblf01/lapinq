from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

import asyncpg

logger = logging.getLogger("lapinq.storage")

RETRY_BACKOFF_SECONDS = (10, 30, 60, 300, 600)

DB_TIMEOUT = float(os.environ.get("LAPINQ_DB_TIMEOUT", "30"))

SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS lapinq_tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_name   TEXT NOT NULL,
    task_name    TEXT NOT NULL,
    module_path  TEXT NOT NULL,
    args         JSONB NOT NULL DEFAULT '[]',
    kwargs       JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','running','completed','failed','cancelled','expired')),
    result       TEXT,
    error        TEXT,
    attempts     INT NOT NULL DEFAULT 0,
    max_retries  INT NOT NULL DEFAULT 3,
    priority     INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_heartbeat TIMESTAMPTZ,
    worker_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON lapinq_tasks(status, created_at);

CREATE INDEX IF NOT EXISTS idx_tasks_scheduled
    ON lapinq_tasks(scheduled_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_tasks_pending_priority
    ON lapinq_tasks(priority DESC, created_at)
    WHERE status = 'pending';
"""

MIGRATIONS: list[str] = [
    """
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS ttl_seconds DOUBLE PRECISION;
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0;
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;
    """,
    """
    ALTER TABLE lapinq_tasks DROP CONSTRAINT IF EXISTS lapinq_tasks_status_check;
    ALTER TABLE lapinq_tasks ADD CONSTRAINT lapinq_tasks_status_check
        CHECK (status IN ('pending','running','completed','failed','cancelled'));
    """,
    """
    ALTER TABLE lapinq_tasks DROP CONSTRAINT IF EXISTS lapinq_tasks_status_check;
    ALTER TABLE lapinq_tasks ADD CONSTRAINT lapinq_tasks_status_check
        CHECK (status IN ('pending','running','completed','failed','cancelled','expired'));
    """,
]

NOTIFY_SQL = """
CREATE OR REPLACE FUNCTION notify_lapinq_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('lapinq_changed', '');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS lapinq_change_trigger ON lapinq_tasks;
CREATE TRIGGER lapinq_change_trigger
AFTER INSERT OR UPDATE ON lapinq_tasks
FOR EACH STATEMENT
EXECUTE FUNCTION notify_lapinq_change();
"""

ALLOWED_FILTER_COLUMNS = frozenset({"queue_name", "status"})


class Storage:
    def __init__(self, pool: asyncpg.Pool, database_url: str | None = None):
        self.pool = pool
        self._database_url = database_url
        self._listener_conn: asyncpg.Connection | None = None
        self._listener_cb: Any = None

    @classmethod
    async def create(cls, database_url: str, max_size: int | None = None, max_retries: int = 5) -> Storage:
        if max_size is None:
            max_size = int(os.environ.get("LAPINQ_POOL_SIZE", "10"))
        # Add 1 for the LISTEN connection
        pool_size = max_size + 1
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                pool = await asyncpg.create_pool(database_url, min_size=1, max_size=pool_size)
                async with pool.acquire() as conn:
                    await conn.execute(SQL_SCHEMA)
                    await conn.execute(NOTIFY_SQL)
                    await _apply_migrations(conn)
                return cls(pool, database_url=database_url)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = (attempt + 1) * 2
                    logger.warning(
                        "DB connection failed (attempt %d/%d): %s — retrying in %ds",
                        attempt + 1, max_retries, e, delay,
                    )
                    await asyncio.sleep(delay)
        raise RuntimeError(f"Could not connect to database after {max_retries} attempts") from last_error

    def _parse_row(self, row: asyncpg.Record | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        for key in ("args", "kwargs"):
            if key in result and isinstance(result[key], str):
                result[key] = json_loads(result[key])
        return result

    async def listen_for_changes(self, callback: Any) -> None:
        if self._database_url:
            conn = await asyncpg.connect(self._database_url)
        else:
            conn = await self.pool.acquire()
        self._listener_cb = lambda *_: callback()
        await conn.add_listener("lapinq_changed", self._listener_cb)
        self._listener_conn = conn

    async def stop_listening(self) -> None:
        if self._listener_conn is not None:
            conn = self._listener_conn
            self._listener_conn = None
            await conn.remove_listener("lapinq_changed", self._listener_cb)
            await conn.close()

    async def close(self) -> None:
        await self.stop_listening()
        await self.pool.close()

    async def enqueue(
        self,
        task_name: str,
        queue_name: str,
        module_path: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        scheduled_at: Any = None,
        max_retries: int = 3,
        priority: int = 0,
        ttl_seconds: float | None = None,
    ) -> uuid.UUID | None:
        if ttl_seconds == 0:
            return None
        async with self.pool.acquire() as conn:
            row = await asyncio.wait_for(
                conn.fetchrow(
                    """
                    INSERT INTO lapinq_tasks
                        (task_name, queue_name, module_path, args, kwargs, status,
                         scheduled_at, max_retries, priority, ttl_seconds)
                    VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, 'pending',
                            COALESCE($6::timestamptz, now()), $7, $8, $9)
                    RETURNING id
                    """,
                    task_name,
                    queue_name,
                    module_path,
                    json_dumps(args or []),
                    json_dumps(kwargs or {}),
                    scheduled_at,
                    max_retries,
                    priority,
                    ttl_seconds,
                ),
                timeout=DB_TIMEOUT,
            )
            return row["id"]

    async def claim_task(
        self,
        worker_id: str,
        statuses: tuple[str, ...] = ("pending",),
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await asyncio.wait_for(
                conn.fetchrow(
                    """
                    UPDATE lapinq_tasks
                    SET status = 'running',
                        started_at = now(),
                        worker_id = $1,
                        last_heartbeat = now()
                    WHERE id = (
                        SELECT id FROM lapinq_tasks
                        WHERE status = ANY($2::text[])
                        AND scheduled_at <= now()
                        ORDER BY priority DESC, created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING *
                    """,
                    worker_id,
                    list(statuses),
                ),
                timeout=DB_TIMEOUT,
            )
            return self._parse_row(row)

    async def complete_task(self, task_id: uuid.UUID, result: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            await asyncio.wait_for(
                conn.execute(
                    """
                    UPDATE lapinq_tasks
                    SET status = 'completed',
                        result = $2,
                        completed_at = now()
                    WHERE id = $1
                    """,
                    task_id,
                    result,
                ),
                timeout=DB_TIMEOUT,
            )

    async def fail_task(self, task_id: uuid.UUID, error: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            row = await asyncio.wait_for(
                conn.fetchrow(
                    "SELECT attempts, max_retries FROM lapinq_tasks WHERE id = $1", task_id
                ),
                timeout=DB_TIMEOUT,
            )
            if row is None:
                return
            attempts = row["attempts"] + 1
            if attempts < row["max_retries"]:
                backoff = _retry_backoff_seconds(attempts)
                await asyncio.wait_for(
                    conn.execute(
                        """
                        UPDATE lapinq_tasks
                        SET status = 'pending',
                            attempts = $2,
                            error = $3,
                            scheduled_at = now() + ($4::text || ' seconds')::interval,
                            started_at = NULL,
                            worker_id = NULL
                        WHERE id = $1
                        """,
                        task_id,
                        attempts,
                        error,
                        str(backoff),
                    ),
                    timeout=DB_TIMEOUT,
                )
            else:
                await asyncio.wait_for(
                    conn.execute(
                        """
                        UPDATE lapinq_tasks
                        SET status = 'failed',
                            attempts = $2,
                            error = $3,
                            completed_at = now()
                        WHERE id = $1
                        """,
                        task_id,
                        attempts,
                        error,
                    ),
                    timeout=DB_TIMEOUT,
                )

    async def heartbeat(self, worker_id: str) -> None:
        async with self.pool.acquire() as conn:
            await asyncio.wait_for(
                conn.execute(
                    "UPDATE lapinq_tasks SET last_heartbeat = now() WHERE worker_id = $1 AND status = 'running'",
                    worker_id,
                ),
                timeout=DB_TIMEOUT,
            )

    async def recover_stale_tasks(self, max_running_seconds: int = 300) -> list[uuid.UUID]:
        async with self.pool.acquire() as conn:
            rows = await asyncio.wait_for(
                conn.fetch(
                    """
                    UPDATE lapinq_tasks
                    SET status = 'pending',
                        started_at = NULL,
                        worker_id = NULL,
                        attempts = attempts + 1,
                        error = 'recovered after timeout'
                    WHERE id = ANY(
                        SELECT id FROM lapinq_tasks
                        WHERE status = 'running'
                        AND started_at < now() - ($1::text || ' seconds')::interval
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id
                    """,
                    str(max_running_seconds),
                ),
                timeout=DB_TIMEOUT,
            )
            return [row["id"] for row in rows]

    async def get_task(self, task_id: uuid.UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await asyncio.wait_for(
                conn.fetchrow("SELECT * FROM lapinq_tasks WHERE id = $1", task_id),
                timeout=DB_TIMEOUT,
            )
            return self._parse_row(row)

    async def get_task_result(self, task_id: uuid.UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await asyncio.wait_for(
                conn.fetchrow(
                    "SELECT id, status, result, error, completed_at FROM lapinq_tasks WHERE id = $1",
                    task_id,
                ),
                timeout=DB_TIMEOUT,
            )
            if row is None:
                return None
            return {
                "id": str(row["id"]),
                "status": row["status"],
                "result": row["result"],
                "error": row["error"],
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            }

    async def list_tasks(
        self,
        queue_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            conditions: list[str] = []
            params: list[Any] = []
            param_idx = 0
            if queue_name:
                param_idx += 1
                conditions.append(f"queue_name = ${param_idx}")
                params.append(queue_name)
            if status:
                param_idx += 1
                conditions.append(f"status = ${param_idx}")
                params.append(status)

            where = " AND ".join(conditions) if conditions else "TRUE"
            param_idx += 1
            query = f"""
                SELECT * FROM lapinq_tasks
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ${param_idx}
            """
            params.append(limit)
            rows = await asyncio.wait_for(conn.fetch(query, *params), timeout=DB_TIMEOUT)
            result: list[dict[str, Any]] = []
            for row in rows:
                parsed = self._parse_row(row)
                if parsed is not None:
                    result.append(parsed)
            return result

    async def list_failed_tasks(
        self, queue_name: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return await self.list_tasks(queue_name=queue_name, status="failed", limit=limit)

    async def requeue_task(self, task_id: uuid.UUID) -> bool:
        async with self.pool.acquire() as conn:
            result = await asyncio.wait_for(
                conn.execute(
                    """
                    UPDATE lapinq_tasks
                    SET status = 'pending',
                        attempts = 0,
                        error = NULL,
                        scheduled_at = now(),
                        started_at = NULL,
                        completed_at = NULL,
                        worker_id = NULL
                    WHERE id = $1 AND status = 'failed'
                    """,
                    task_id,
                ),
                timeout=DB_TIMEOUT,
            )
            return result != "UPDATE 0"

    async def queue_stats(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await asyncio.wait_for(
                conn.fetch(
                    """
                    SELECT
                        queue_name,
                        COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                        COUNT(*) FILTER (WHERE status = 'running') AS running,
                        COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                        COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                        COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled
                    FROM lapinq_tasks
                    GROUP BY queue_name
                    ORDER BY queue_name
                    """
                ),
                timeout=DB_TIMEOUT,
            )
            return [dict(row) for row in rows]

    async def cancel_task(self, task_id: uuid.UUID) -> bool:
        async with self.pool.acquire() as conn:
            result = await asyncio.wait_for(
                conn.execute(
                    """
                    UPDATE lapinq_tasks
                    SET status = 'cancelled',
                        completed_at = now(),
                        error = 'cancelled by user'
                    WHERE id = $1 AND status = 'pending'
                    """,
                    task_id,
                ),
                timeout=DB_TIMEOUT,
            )
            return result != "UPDATE 0"

    async def cleanup_expired_tasks(self) -> int:
        async with self.pool.acquire() as conn:
            result = await asyncio.wait_for(
                conn.execute(
                    """
                    UPDATE lapinq_tasks
                    SET status = 'expired',
                        completed_at = now(),
                        error = 'ttl expired'
                    WHERE ttl_seconds IS NOT NULL
                      AND ttl_seconds > 0
                      AND status NOT IN ('completed', 'failed', 'cancelled', 'expired')
                      AND created_at + (ttl_seconds::text || ' seconds')::interval < now()
                    """
                ),
                timeout=DB_TIMEOUT,
            )
            count = int(result.split()[-1]) if result else 0
            if count:
                logger.info("Expired %d tasks by TTL", count)
            return count

    async def archive_old_tasks(
        self, max_age_days: float = 30, batch_size: int = 1000
    ) -> int:
        async with self.pool.acquire() as conn:
            result = await asyncio.wait_for(
                conn.execute(
                    """
                    DELETE FROM lapinq_tasks
                    WHERE status IN ('completed', 'failed', 'cancelled', 'expired')
                      AND completed_at < now() - ($1::text || ' days')::interval
                    LIMIT $2
                    """,
                    str(max_age_days),
                    batch_size,
                ),
                timeout=DB_TIMEOUT,
            )
            count = int(result.split()[-1]) if result else 0
            if count:
                logger.info("Archived %d old tasks (age > %sd)", count, max_age_days)
            return count


async def _apply_migrations(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS lapinq_schema_version (version INT PRIMARY KEY)"
    )
    current = await conn.fetchval(
        "SELECT COALESCE(MAX(version), 0) FROM lapinq_schema_version"
    )
    if current == 0:
        await conn.execute(
            "INSERT INTO lapinq_schema_version (version) VALUES (0) ON CONFLICT DO NOTHING"
        )
    for i, migration_sql in enumerate(MIGRATIONS):
        version = i + 1
        if version > current:
            await conn.execute(migration_sql)
            await conn.execute("UPDATE lapinq_schema_version SET version = $1", version)
            logger.info("Applied schema migration v%d", version)


def _retry_backoff_seconds(attempt: int) -> int:
    if attempt <= 0:
        return 0
    if attempt > len(RETRY_BACKOFF_SECONDS):
        return RETRY_BACKOFF_SECONDS[-1]
    return RETRY_BACKOFF_SECONDS[attempt - 1]


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str)


def json_loads(data: str | bytes) -> Any:
    import json

    return json.loads(data)
