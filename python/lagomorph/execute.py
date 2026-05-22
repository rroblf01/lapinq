from __future__ import annotations

import importlib
import os
import sys
import uuid

import asyncpg


async def execute_task(task_id: str) -> None:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/lagomorph"
    )
    tid = uuid.UUID(task_id)

    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow(
            "SELECT * FROM lagomorph_tasks WHERE id = $1", tid
        )
        if row is None:
            print(f"Task {task_id} not found", file=sys.stderr)
            sys.exit(1)

        task = dict(row)
        module_path = task["module_path"]
        task_name = task["task_name"]
        args = task["args"] or []
        kwargs = task["kwargs"] or {}

        module = importlib.import_module(module_path)
        func_name = task_name.split(".")[-1]
        func = getattr(module, func_name, None)
        if func is None:
            func_name = task_name.rsplit(".", 1)[-1]
            func = getattr(module, func_name, None)

        if func is None:
            print(
                f"Function {task_name} not found in module {module_path}",
                file=sys.stderr,
            )
            await conn.execute(
                "DELETE FROM lagomorph_tasks WHERE id = $1", tid
            )
            sys.exit(1)

        result = func(*args, **kwargs)
        print(f"Task {task_id} completed: {result}")
    except Exception as e:
        print(f"Task {task_id} failed: {e}", file=sys.stderr)
        await conn.execute("DELETE FROM lagomorph_tasks WHERE id = $1", tid)
        sys.exit(1)
    finally:
        await conn.close()
