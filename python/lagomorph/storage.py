from __future__ import annotations

import uuid
from typing import Any

import asyncpg

RETRY_BACKOFF_SECONDS = (10, 30, 60, 300, 600)

SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS lagomorph_tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_name   TEXT NOT NULL,
    task_name    TEXT NOT NULL,
    module_path  TEXT NOT NULL,
    args         JSONB NOT NULL DEFAULT '[]',
    kwargs       JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','running','completed','failed')),
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

ALTER TABLE lagomorph_tasks ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0;
ALTER TABLE lagomorph_tasks ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON lagomorph_tasks(status, created_at);

CREATE INDEX IF NOT EXISTS idx_tasks_scheduled
    ON lagomorph_tasks(scheduled_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_tasks_pending_priority
    ON lagomorph_tasks(priority DESC, created_at)
    WHERE status = 'pending';
"""


class Storage:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, database_url: str, max_size: int = 10) -> Storage:
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=max_size)
        async with pool.acquire() as conn:
            await conn.execute(SQL_SCHEMA)
        return cls(pool)

    def _parse_row(self, row: asyncpg.Record | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        for key in ("args", "kwargs"):
            if key in result and isinstance(result[key], str):
                result[key] = json_loads(result[key])
        return result

    async def close(self) -> None:
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
    ) -> uuid.UUID:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO lagomorph_tasks
                    (task_name, queue_name, module_path, args, kwargs, status,
                     scheduled_at, max_retries, priority)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, 'pending',
                        COALESCE($6::timestamptz, now()), $7, $8)
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
            )
            return row["id"]

    async def claim_task(
        self,
        worker_id: str,
        statuses: tuple[str, ...] = ("pending",),
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE lagomorph_tasks
                SET status = 'running',
                    started_at = now(),
                    worker_id = $1,
                    last_heartbeat = now()
                WHERE id = (
                    SELECT id FROM lagomorph_tasks
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
            )
            return self._parse_row(row)

    async def complete_task(self, task_id: uuid.UUID, result: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE lagomorph_tasks
                SET status = 'completed',
                    result = $2,
                    completed_at = now()
                WHERE id = $1
                """,
                task_id,
                result,
            )

    async def fail_task(self, task_id: uuid.UUID, error: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT attempts, max_retries FROM lagomorph_tasks WHERE id = $1", task_id
            )
            if row is None:
                return
            attempts = row["attempts"] + 1
            if attempts < row["max_retries"]:
                backoff = _retry_backoff_seconds(attempts)
                await conn.execute(
                    """
                    UPDATE lagomorph_tasks
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
                )
            else:
                await conn.execute(
                    """
                    UPDATE lagomorph_tasks
                    SET status = 'failed',
                        attempts = $2,
                        error = $3,
                        completed_at = now()
                    WHERE id = $1
                    """,
                    task_id,
                    attempts,
                    error,
                )

    async def heartbeat(self, worker_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE lagomorph_tasks SET last_heartbeat = now() WHERE worker_id = $1 AND status = 'running'",
                worker_id,
            )

    async def recover_stale_tasks(self, max_running_seconds: int = 300) -> list[uuid.UUID]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE lagomorph_tasks
                SET status = 'pending',
                    started_at = NULL,
                    worker_id = NULL,
                    attempts = attempts + 1,
                    error = 'recovered after timeout'
                WHERE id = ANY(
                    SELECT id FROM lagomorph_tasks
                    WHERE status = 'running'
                    AND started_at < now() - ($1::text || ' seconds')::interval
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id
                """,
                str(max_running_seconds),
            )
            return [row["id"] for row in rows]

    async def get_task(self, task_id: uuid.UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM lagomorph_tasks WHERE id = $1", task_id)
            return self._parse_row(row)

    async def list_tasks(
        self,
        queue_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            conditions = []
            params: list[Any] = []
            if queue_name:
                conditions.append(f"queue_name = ${len(params) + 1}")
                params.append(queue_name)
            if status:
                conditions.append(f"status = ${len(params) + 1}")
                params.append(status)

            where = " AND ".join(conditions) if conditions else "TRUE"
            query = f"""
                SELECT * FROM lagomorph_tasks
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ${len(params) + 1}
            """
            params.append(limit)
            rows = await conn.fetch(query, *params)
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
            result = await conn.execute(
                """
                UPDATE lagomorph_tasks
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
            )
            return result != "UPDATE 0"

    async def queue_stats(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    queue_name,
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'running') AS running,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM lagomorph_tasks
                GROUP BY queue_name
                ORDER BY queue_name
                """
            )
            return [dict(row) for row in rows]

    async def cancel_task(self, task_id: uuid.UUID) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM lagomorph_tasks
                WHERE id = $1 AND status = 'pending'
                """,
                task_id,
            )
            return result != "DELETE 0"


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
