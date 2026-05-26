from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import uuid
from typing import Any

import asyncpg

logger = logging.getLogger("lapinq.storage")

RETRY_BACKOFF_SECONDS = (10, 30, 60, 300, 600)

DB_TIMEOUT = float(os.environ.get("LAPINQ_DB_TIMEOUT", "30"))

PBKDF2_ITERATIONS = 600_000

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

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS lapinq_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user'
        CHECK (role IN ('admin', 'user')),
    permissions JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
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
    """
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS progress DOUBLE PRECISION;
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS progress_message TEXT;
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS retry_delay DOUBLE PRECISION;
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS retry_backoff BOOLEAN DEFAULT TRUE;
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS webhook_url TEXT;
    """,
    USERS_SCHEMA,
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
            pool: asyncpg.Pool | None = None
            try:
                pool = await asyncpg.create_pool(database_url, min_size=1, max_size=pool_size)
                async with pool.acquire() as conn:
                    await conn.execute(SQL_SCHEMA)
                    await conn.execute(NOTIFY_SQL)
                    await _apply_migrations(conn)
                store = cls(pool, database_url=database_url)
                await store.ensure_default_admin()
                return store
            except Exception as e:
                last_error = e
                if pool is not None:
                    await pool.close()
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
        for key in ("args", "kwargs", "metadata"):
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

    # ── Auth ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
        return f"pbkdf2:sha256:{PBKDF2_ITERATIONS}:{salt}:{base64.b64encode(h).decode()}"

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        try:
            parts = stored.split(":")
            if len(parts) != 5 or parts[0] != "pbkdf2" or parts[1] != "sha256":
                return False
            iterations = int(parts[2])
            salt = parts[3]
            expected = base64.b64decode(parts[4])
            h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
            return hmac.compare_digest(h, expected)
        except (ValueError, IndexError, Exception):
            return False

    async def ensure_default_admin(self) -> None:
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM lapinq_users LIMIT 1")
            if not exists:
                pw = self._hash_password("lapinq")
                await conn.execute(
                    "INSERT INTO lapinq_users (username, password_hash, role) VALUES ($1, $2, 'admin')",
                    "lapinq", pw,
                )
                logger.info("Created default admin user 'lapinq'")

    async def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, username, password_hash, role, permissions FROM lapinq_users WHERE username = $1",
                username,
            )
            if row is None:
                return None
            if not self._verify_password(password, row["password_hash"]):
                return None
            return {
                "id": str(row["id"]),
                "username": row["username"],
                "role": row["role"],
                "permissions": row["permissions"] if isinstance(row["permissions"], dict) else {},
            }

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, username, role, permissions, created_at FROM lapinq_users WHERE id = $1::uuid",
                user_id,
            )
            if row is None:
                return None
            return {
                "id": str(row["id"]),
                "username": row["username"],
                "role": row["role"],
                "permissions": row["permissions"] if isinstance(row["permissions"], dict) else {},
                "created_at": row["created_at"].isoformat(),
            }

    async def create_user(self, username: str, password: str, role: str = "user") -> dict[str, Any]:
        pw = self._hash_password(password)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO lapinq_users (username, password_hash, role)"
                " VALUES ($1, $2, $3) RETURNING id, username, role, created_at",
                username, pw, role,
            )
            return {
                "id": str(row["id"]),
                "username": row["username"],
                "role": row["role"],
                "created_at": row["created_at"].isoformat(),
            }

    async def list_users(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, username, role, permissions, created_at FROM lapinq_users ORDER BY created_at"
            )
            return [
                {
                    "id": str(r["id"]),
                    "username": r["username"],
                    "role": r["role"],
                    "permissions": r["permissions"] if isinstance(r["permissions"], dict) else {},
                    "created_at": r["created_at"].isoformat(),
                }
                for r in rows
            ]

    async def update_password(self, user_id: str, new_password: str) -> bool:
        pw = self._hash_password(new_password)
        async with self.pool.acquire() as conn:
            r = await conn.execute(
                "UPDATE lapinq_users SET password_hash = $1, updated_at = now() WHERE id = $2::uuid",
                pw, user_id,
            )
            return r != "UPDATE 0"

    async def update_role(self, user_id: str, new_role: str) -> bool:
        async with self.pool.acquire() as conn:
            r = await conn.execute(
                "UPDATE lapinq_users SET role = $1, updated_at = now() WHERE id = $2::uuid",
                new_role, user_id,
            )
            return r != "UPDATE 0"

    async def update_permissions(self, user_id: str, permissions: dict[str, Any]) -> bool:
        async with self.pool.acquire() as conn:
            r = await conn.execute(
                "UPDATE lapinq_users SET permissions = $1::jsonb, updated_at = now() WHERE id = $2::uuid",
                json.dumps(permissions), user_id,
            )
            return r != "UPDATE 0"

    async def delete_user(self, user_id: str) -> bool:
        async with self.pool.acquire() as conn:
            r = await conn.execute("DELETE FROM lapinq_users WHERE id = $1::uuid", user_id)
            return r != "DELETE 0"

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
        metadata: dict[str, Any] | None = None,
        retry_delay: float | None = None,
        retry_backoff: bool | None = None,
        webhook_url: str | None = None,
    ) -> uuid.UUID | None:
        if ttl_seconds == 0:
            return None
        async with self.pool.acquire() as conn:
            row = await asyncio.wait_for(
                conn.fetchrow(
                    """
                    INSERT INTO lapinq_tasks
                        (task_name, queue_name, module_path, args, kwargs, status,
                         scheduled_at, max_retries, priority, ttl_seconds,
                         metadata, retry_delay, retry_backoff, webhook_url)
                    VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, 'pending',
                            COALESCE($6::timestamptz, now()), $7, $8, $9,
                            $10::jsonb, $11, $12, $13)
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
                    json_dumps(metadata or {}),
                    retry_delay,
                    retry_backoff if retry_backoff is not None else True,
                    webhook_url,
                ),
                timeout=DB_TIMEOUT,
            )
            return row["id"]

    async def enqueue_batch(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[uuid.UUID]:
        ids: list[uuid.UUID] = []
        async with self.pool.acquire() as conn:
            for t in tasks:
                if t.get("ttl_seconds") == 0:
                    continue
                row = await asyncio.wait_for(
                    conn.fetchrow(
                        """
                        INSERT INTO lapinq_tasks
                            (task_name, queue_name, module_path, args, kwargs, status,
                             scheduled_at, max_retries, priority, ttl_seconds,
                             metadata, retry_delay, retry_backoff, webhook_url)
                        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, 'pending',
                                COALESCE($6::timestamptz, now()), $7, $8, $9,
                                $10::jsonb, $11, $12, $13)
                        RETURNING id
                        """,
                        t["task_name"],
                        t.get("queue_name", "default"),
                        t.get("module_path", ""),
                        json_dumps(t.get("args", [])),
                        json_dumps(t.get("kwargs", {})),
                        t.get("scheduled_at"),
                        t.get("max_retries", 3),
                        t.get("priority", 0),
                        t.get("ttl_seconds"),
                        json_dumps(t.get("metadata", {})),
                        t.get("retry_delay"),
                        t.get("retry_backoff", True),
                        t.get("webhook_url"),
                    ),
                    timeout=DB_TIMEOUT,
                )
                ids.append(row["id"])
        return ids

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
                    "SELECT attempts, max_retries, retry_delay, retry_backoff FROM lapinq_tasks WHERE id = $1",
                    task_id,
                ),
                timeout=DB_TIMEOUT,
            )
            if row is None:
                return
            attempts = row["attempts"] + 1
            if attempts < row["max_retries"]:
                if row["retry_backoff"]:
                    backoff = _retry_backoff_seconds(attempts)
                elif row["retry_delay"] is not None:
                    backoff = row["retry_delay"]
                else:
                    backoff = 10
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

    async def update_progress(
        self, task_id: uuid.UUID, progress: float, message: str | None = None
    ) -> None:
        async with self.pool.acquire() as conn:
            await asyncio.wait_for(
                conn.execute(
                    """
                    UPDATE lapinq_tasks
                    SET progress = $2, progress_message = $3
                    WHERE id = $1
                    """,
                    task_id,
                    progress,
                    message,
                ),
                timeout=DB_TIMEOUT,
            )

    async def update_task_metadata(
        self, task_id: uuid.UUID, metadata: dict[str, Any]
    ) -> None:
        async with self.pool.acquire() as conn:
            await asyncio.wait_for(
                conn.execute(
                    """
                    UPDATE lapinq_tasks
                    SET metadata = metadata || $2::jsonb
                    WHERE id = $1
                    """,
                    task_id,
                    json_dumps(metadata),
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
        task_name: str | None = None,
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
            if task_name:
                param_idx += 1
                conditions.append(f"task_name ILIKE ${param_idx}")
                params.append(f"%{task_name}%")

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

    async def delete_tasks(
        self,
        queue_name: str | None = None,
        status: str | None = None,
        task_name: str | None = None,
        args_search: str | None = None,
        result_search: str | None = None,
        error_search: str | None = None,
    ) -> int:
        async with self.pool.acquire() as conn:
            conditions: list[str] = []
            params: list[Any] = []
            idx = 0
            if queue_name:
                idx += 1
                conditions.append(f"queue_name = ${idx}")
                params.append(queue_name)
            if status:
                idx += 1
                conditions.append(f"status = ${idx}")
                params.append(status)
            if task_name:
                idx += 1
                conditions.append(f"task_name ILIKE ${idx}")
                params.append(f"%{task_name}%")
            if args_search:
                idx += 1
                conditions.append(f"args::text ILIKE ${idx}")
                params.append(f"%{args_search}%")
            if result_search:
                idx += 1
                conditions.append(f"result ILIKE ${idx}")
                params.append(f"%{result_search}%")
            if error_search:
                idx += 1
                conditions.append(f"error ILIKE ${idx}")
                params.append(f"%{error_search}%")
            where = " AND ".join(conditions) if conditions else "TRUE"
            result = await asyncio.wait_for(
                conn.execute(f"DELETE FROM lapinq_tasks WHERE {where}", *params),
                timeout=DB_TIMEOUT,
            )
            count = int(result.split()[-1]) if result else 0
            if count:
                logger.info("Deleted %d tasks by filter", count)
            return count

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
            await conn.execute(
                "INSERT INTO lapinq_schema_version (version) VALUES ($1) ON CONFLICT DO NOTHING",
                version,
            )
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
