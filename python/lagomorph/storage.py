from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg


SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS lagomorph_tasks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_name  TEXT NOT NULL,
    task_name   TEXT NOT NULL,
    module_path TEXT NOT NULL,
    args        JSONB NOT NULL DEFAULT '[]',
    kwargs      JSONB NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','completed','failed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    worker_id   TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON lagomorph_tasks(status, created_at);
"""


class Storage:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, database_url: str, max_size: int = 10) -> Storage:
        pool = await asyncpg.create_pool(
            database_url, min_size=2, max_size=max_size
        )
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
    ) -> uuid.UUID:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO lagomorph_tasks
                    (task_name, queue_name, module_path, args, kwargs, status)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, 'pending')
                RETURNING id
                """,
                task_name,
                queue_name,
                module_path,
                json_dumps(args or []),
                json_dumps(kwargs or {}),
            )
            return row["id"]

    async def claim_task(
        self, worker_id: str, statuses: tuple[str, ...] = ("pending",)
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE lagomorph_tasks
                SET status = 'running',
                    started_at = now(),
                    worker_id = $1
                WHERE id = (
                    SELECT id FROM lagomorph_tasks
                    WHERE status = ANY($2::text[])
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING *
                """,
                worker_id,
                list(statuses),
            )
            return self._parse_row(row)

    async def complete_task(self, task_id: uuid.UUID) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM lagomorph_tasks WHERE id = $1", task_id
            )

    async def fail_task(self, task_id: uuid.UUID, error: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM lagomorph_tasks WHERE id = $1", task_id
            )

    async def get_task(self, task_id: uuid.UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM lagomorph_tasks WHERE id = $1", task_id
            )
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
            return [self._parse_row(row) for row in rows if row is not None]

    async def queue_stats(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    queue_name,
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'running') AS running
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


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str)


def json_loads(data: str | bytes) -> Any:
    import json

    return json.loads(data)
