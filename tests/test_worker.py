from __future__ import annotations

import asyncio
import contextlib
import os
import signal

import pytest
from lapinq.storage import Storage

from tests.helpers import poll_until

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lapinq_test"


async def test_worker_claims_and_processes_task():
    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("test_fn", "default", "tests.test_worker")
        assert task_id is not None
        claimed = await storage.claim_task("test-worker-1")
        assert claimed is not None
        assert claimed["id"] == task_id
        assert claimed["status"] == "running"
    finally:
        await storage.close()


async def test_execute_imports_and_runs_function():
    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("dummy_task", "default", "tests.test_worker")
        assert task_id is not None
        await storage.claim_task("test-worker-2")
        await storage.complete_task(task_id, result='"ok"')
        done = await storage.get_task(task_id)
        assert done is not None
        assert done["status"] == "completed"
    finally:
        await storage.close()


async def test_execute_module_loads_function():
    from lapinq.storage import Storage

    storage = await Storage.create(DATABASE_URL)
    try:
        await storage.enqueue(
            "dummy",
            "default",
            "tests.test_worker",
            args=[1, 2],
            kwargs={"x": "y"},
        )
        claimed = await storage.claim_task("test-exec")
        assert claimed is not None
        assert claimed["task_name"] == "dummy"
        assert claimed["args"] == [1, 2]
        assert claimed["kwargs"] == {"x": "y"}
    finally:
        await storage.close()


async def test_handle_signal_sets_event():
    from lapinq.worker import _handle_signal

    event = asyncio.Event()
    _handle_signal(signal.SIGTERM, event, "test-wid")
    assert event.is_set()


async def test_heartbeat_loop_updates_on_each_iteration(monkeypatch):
    import lapinq.worker as wmod

    monkeypatch.setattr(wmod, "HEARTBEAT_INTERVAL", 0.05)
    from lapinq.worker import _heartbeat_loop

    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("hb_test", "default", "tests.test_worker")
        assert task_id is not None
        await storage.claim_task("hb-worker")

        shutdown_event = asyncio.Event()

        async def run_and_stop():
            task = asyncio.create_task(_heartbeat_loop(storage, "hb-worker", shutdown_event))
            await asyncio.sleep(0.05)
            shutdown_event.set()
            await task

        await run_and_stop()

        task = await storage.get_task(task_id)
        assert task is not None
        assert task["last_heartbeat"] is not None
    finally:
        await storage.close()


async def test_heartbeat_loop_does_not_error_for_unknown_worker(monkeypatch):
    import lapinq.worker as wmod

    monkeypatch.setattr(wmod, "HEARTBEAT_INTERVAL", 0.05)
    from lapinq.worker import _heartbeat_loop

    shutdown_event = asyncio.Event()
    storage = await Storage.create(DATABASE_URL)
    try:
        task = asyncio.create_task(_heartbeat_loop(storage, "nonexistent", shutdown_event))
        await asyncio.sleep(0.05)
        shutdown_event.set()
        await task
    finally:
        await storage.close()


async def _sleep_forever() -> None:
    await asyncio.sleep(999)


@pytest.mark.slow
async def test_process_task_timeout(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    import lapinq.worker as wmod
    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("_sleep_forever", "test_timeout", "tests.test_worker", max_retries=0)
        assert task_id is not None

        worker_task = asyncio.create_task(
            wmod.run_worker(database_url=DATABASE_URL, concurrency=1, poll_interval=0.05, task_timeout=0.3)
        )

        async def get_failed():
            t = await storage.get_task(task_id)
            return t if t and t["status"] == "failed" else None
        task = await poll_until(get_failed, timeout=3)
        assert task is not None
        assert task["error"] == "timed out"

        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
    finally:
        await storage.close()


async def test_heartbeat_error_does_not_crash_loop(monkeypatch):
    import lapinq.worker as wmod
    monkeypatch.setattr(wmod, "HEARTBEAT_INTERVAL", 0.05)

    from lapinq.worker import _heartbeat_loop
    storage = await Storage.create(DATABASE_URL)
    try:
        import lapinq.storage as smod
        original = smod.Storage.heartbeat

        call_count = 0

        async def broken_heartbeat(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("broken")
            return await original(storage, *a, **kw)

        monkeypatch.setattr(smod.Storage, "heartbeat", broken_heartbeat)

        task_id = await storage.enqueue("hb_err", "default", "tests.test_worker")
        assert task_id is not None
        await storage.claim_task("hb-err-worker")

        shutdown_event = asyncio.Event()
        hb_task = asyncio.create_task(_heartbeat_loop(storage, "hb-err-worker", shutdown_event))
        await asyncio.sleep(0.2)
        shutdown_event.set()
        await hb_task

        assert call_count >= 2

        task = await storage.get_task(task_id)
        assert task is not None
        assert task["last_heartbeat"] is not None
    finally:
        await storage.close()


async def test_run_worker_inline_processes_task(monkeypatch):
    import lapinq.worker as wmod

    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("add", "test_inline", "tests.test_execute", args=[3, 4])
        assert task_id is not None

        worker_task = asyncio.create_task(
            wmod.run_worker_inline(storage, concurrency=2, poll_interval=0.05, task_timeout=30)
        )

        async def get_completed():
            t = await storage.get_task(task_id)
            return t if t and t["status"] == "completed" else None
        task = await poll_until(get_completed, timeout=3)
        assert task is not None
        assert task["result"] == "7"

        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
    finally:
        await storage.close()


@pytest.mark.slow
async def test_run_worker_inline_handles_timeout(monkeypatch):
    import lapinq.worker as wmod

    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("_sleep_forever", "test_inline_timeout", "tests.test_worker", max_retries=0)
        assert task_id is not None

        worker_task = asyncio.create_task(
            wmod.run_worker_inline(storage, concurrency=1, poll_interval=0.05, task_timeout=0.3)
        )

        async def get_failed():
            t = await storage.get_task(task_id)
            return t if t and t["status"] == "failed" else None
        task = await poll_until(get_failed, timeout=3)
        assert task is not None
        assert task["error"] == "timed out"

        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
    finally:
        await storage.close()


@pytest.mark.slow
async def test_run_worker_loop_processes_task(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)

    import lapinq.worker as wmod

    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("add", "test_worker_loop", "tests.test_execute", args=[1, 2])
        assert task_id is not None

        worker_task = asyncio.create_task(
            wmod.run_worker(database_url=DATABASE_URL, concurrency=2, poll_interval=0.05, task_timeout=30)
        )

        async def get_completed():
            t = await storage.get_task(task_id)
            return t if t and t["status"] == "completed" else None
        task = await poll_until(get_completed, timeout=3)
        assert task is not None

        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
    finally:
        await storage.close()


@pytest.mark.slow
async def test_rust_worker_binary_processes_task():
    import sys

    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue(
            "add", "test_rust_bin", "tests.test_execute",
            args=[10, 20], max_retries=0,
        )
        assert task_id is not None

        binary = "target/release/lapinq-worker"
        if not os.path.exists(binary):
            binary = "target/debug/lapinq-worker"

        proc = await asyncio.create_subprocess_exec(
            binary,
            "--database-url", DATABASE_URL,
            "--concurrency", "2",
            "--poll-interval-secs", "0.05",
            "--task-timeout-secs", "10",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "DATABASE_URL": DATABASE_URL, "LAPINQ_PYTHON": sys.executable},
        )

        async def get_completed():
            t = await storage.get_task(task_id)
            return t if t and t["status"] == "completed" else None
        task = await poll_until(get_completed, timeout=15)
        if task is None:
            task = await storage.get_task(task_id)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=2)
            except (asyncio.TimeoutError, TimeoutError):
                proc.kill()
                stdout, stderr = await proc.communicate()
            msg = "Task not completed"
            if task:
                msg += f" (status={task['status']}, error={task.get('error')})"
            if stderr:
                msg += f"\nRust worker stderr:\n{stderr.decode(errors='replace')}"
            if stdout:
                msg += f"\nRust worker stdout:\n{stdout.decode(errors='replace')}"
            pytest.fail(msg)
        assert task["status"] == "completed", f"Task status: {task['status']}, error: {task.get('error')}"
        assert task["result"] == "30"

        proc.kill()
        await proc.wait()
    finally:
        await storage.close()
