from __future__ import annotations

import asyncio
import os
import sys

from lagomorph.execute import execute_task_inline
from lagomorph.storage import Storage

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lagomorph_test"


def add(a: int, b: int) -> int:
    return a + b


async def async_echo(msg: str) -> str:
    return f"echo:{msg}"


def fail_func() -> None:
    raise RuntimeError("expected failure")


async def test_execute_success():
    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("add", "default", "tests.test_execute", args=[2, 3])
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "lagomorph", "execute", str(task_id),
            env={**os.environ, "DATABASE_URL": DATABASE_URL},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        assert proc.returncode == 0
        assert stdout.decode().strip() == "5"
    finally:
        await storage.close()


async def test_execute_async_function():
    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("async_echo", "default", "tests.test_execute", args=["hello"])
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "lagomorph", "execute", str(task_id),
            env={**os.environ, "DATABASE_URL": DATABASE_URL},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        assert proc.returncode == 0
        assert stdout.decode().strip() == "echo:hello"
    finally:
        await storage.close()


async def test_execute_task_not_found():
    import uuid
    fake_id = str(uuid.uuid4())
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "lagomorph", "execute", fake_id,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    assert proc.returncode == 1
    assert "not found" in stderr.decode()


async def test_execute_inline_sync():
    task_data = {
        "module_path": "tests.test_execute",
        "task_name": "add",
        "args": [10, 20],
        "kwargs": {},
    }
    result = await execute_task_inline(task_data)
    assert result == 30


async def test_execute_inline_async():
    task_data = {
        "module_path": "tests.test_execute",
        "task_name": "async_echo",
        "args": ["world"],
        "kwargs": {},
    }
    result = await execute_task_inline(task_data)
    assert result == "echo:world"


async def test_execute_inline_missing_function():
    task_data = {
        "module_path": "tests.test_execute",
        "task_name": "nonexistent_func",
        "args": [],
        "kwargs": {},
    }
    try:
        await execute_task_inline(task_data)
        raise AssertionError("expected ImportError")
    except ImportError:
        pass


async def test_execute_inline_function_raises():
    task_data = {
        "module_path": "tests.test_execute",
        "task_name": "fail_func",
        "args": [],
        "kwargs": {},
    }
    try:
        await execute_task_inline(task_data)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "expected failure" in str(e)


async def test_execute_function_raises():
    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("fail_func", "default", "tests.test_execute")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "lagomorph", "execute", str(task_id),
            env={**os.environ, "DATABASE_URL": DATABASE_URL},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        assert proc.returncode == 1
        assert "expected failure" in stderr.decode()
    finally:
        await storage.close()
