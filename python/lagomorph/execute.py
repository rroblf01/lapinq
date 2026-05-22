from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
import sys
import uuid
from typing import Any

import asyncpg

from lagomorph.storage import json_loads

logger = logging.getLogger("lagomorph.execute")

try:
    from lagomorph._worker import execute_task_inline as _execute_rust  # ty: ignore
    logger.info("Rust task executor available")
except ImportError:
    _execute_rust = None
    logger.debug("Rust task executor not available, using Python")


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
        return await func(*args, **kwargs)

    if _execute_rust is not None:
        try:
            import json

            return json.loads(_execute_rust(task_data))
        except TypeError:
            pass
        except Exception:
            pass

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def execute_task(task_id: str) -> None:
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lagomorph")
    tid = uuid.UUID(task_id)

    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow("SELECT * FROM lagomorph_tasks WHERE id = $1", tid)
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
    except Exception as e:
        logger.exception("Task %s failed: %s", task_id, e)
        sys.exit(1)
    finally:
        await conn.close()
