from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import os
import sys
import uuid
from typing import Any

import asyncpg

from lapinq.storage import json_loads

logger = logging.getLogger("lapinq.execute")

try:
    from lapinq._worker import execute_task_inline as _execute_rust  # type: ignore
    logger.info("Rust task executor available")
except ImportError:
    _execute_rust = None
    logger.debug("Rust task executor not available, using Python")


class Retry(Exception):
    """Raise this inside a task function to trigger a retry with optional countdown delay."""

    def __init__(self, countdown: float = 10, message: str | None = None):
        self.countdown = countdown
        self.message = message
        super().__init__(message or f"Retry in {countdown}s")


async def _fire_webhook(
    webhook_url: str,
    task_id: uuid.UUID,
    status: str,
    result: str | None = None,
    error: str | None = None,
) -> None:
    """Fire a webhook callback for task completion/failure."""
    try:
        import httpx
        payload = {
            "task_id": str(task_id),
            "status": status,
            "result": result,
            "error": error,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(webhook_url, json=payload)
    except Exception:
        logger.exception("Webhook callback failed for task %s to %s", task_id, webhook_url)


async def execute_task_inline(task_data: dict[str, Any]) -> Any:
    module_path = task_data["module_path"]
    task_name = task_data["task_name"]
    args = task_data.get("args") or []
    kwargs = task_data.get("kwargs") or {}

    module = importlib.import_module(module_path)
    func_name = task_name.rsplit(".", 1)[-1]
    func = getattr(module, func_name, None)

    if func is None:
        raise ImportError(f"Function {task_name} not found in module {module_path}")

    if inspect.iscoroutinefunction(func):
        try:
            return await func(*args, **kwargs)
        except Retry as r:
            raise r
    else:
        if _execute_rust is not None:
            try:
                import json
                _rust_fn = _execute_rust
                loop = asyncio.get_running_loop()
                raw = await loop.run_in_executor(None, lambda: _rust_fn(task_data))
                return json.loads(raw)
            except TypeError as e:
                logger.debug("Rust executor rejected task %s: %s", task_name, e)
            except Retry:
                raise
            except Exception as e:
                logger.warning("Rust executor failed for %s, falling back to Python: %s", task_name, e)

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
        except Retry:
            raise


async def execute_task(task_id: str) -> None:
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lapinq")
    tid = uuid.UUID(task_id)

    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow("SELECT * FROM lapinq_tasks WHERE id = $1", tid)
        if row is None:
            logger.error("Task %s not found", task_id)
            sys.exit(1)

        task = dict(row)
        module_path = task["module_path"]
        task_name = task["task_name"]
        raw_args = task.get("args", "[]")
        raw_kwargs = task.get("kwargs", "{}")
        args = json_loads(raw_args) if isinstance(raw_args, str) else (raw_args or [])
        kwargs = json_loads(raw_kwargs) if isinstance(raw_kwargs, str) else (raw_kwargs or {})

        module = importlib.import_module(module_path)
        func_name = task_name.rsplit(".", 1)[-1]
        func = getattr(module, func_name, None)

        if func is None:
            logger.error("Function %s not found in module %s", task_name, module_path)
            sys.exit(1)

        if inspect.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            result = func(*args, **kwargs)
        print(result, flush=True)
        logger.info("Task %s completed: %s", task_id, result)
    except Retry as r:
        countdown = r.countdown
        await conn.execute(
            """
            UPDATE lapinq_tasks
            SET status = 'pending',
                attempts = attempts + 1,
                error = $2,
                scheduled_at = now() + ($3::text || ' seconds')::interval,
                started_at = NULL,
                worker_id = NULL
            WHERE id = $1
            """,
            tid,
            r.message or "manual retry",
            str(countdown),
        )
        logger.info("Task %s manually retried in %ss", task_id, countdown)
        sys.exit(0)
    except Exception as e:
        logger.exception("Task %s failed: %s", task_id, e)
        sys.exit(1)
    finally:
        await conn.close()
