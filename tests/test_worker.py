from __future__ import annotations

import asyncio
import signal

from lagomorph.storage import Storage

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lagomorph_test"


async def test_worker_claims_and_processes_task():
    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("test_fn", "default", "tests.test_worker")
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
        await storage.claim_task("test-worker-2")
        await storage.complete_task(task_id, result='"ok"')
        done = await storage.get_task(task_id)
        assert done is not None
        assert done["status"] == "completed"
    finally:
        await storage.close()


async def test_execute_module_loads_function():
    from lagomorph.storage import Storage

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
    from lagomorph.worker import _handle_signal

    event = asyncio.Event()
    _handle_signal(signal.SIGTERM, event, "test-wid")
    assert event.is_set()


async def test_heartbeat_loop_updates_on_each_iteration():
    from lagomorph.worker import _heartbeat_loop

    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("hb_test", "default", "tests.test_worker")
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


async def test_heartbeat_loop_does_not_error_for_unknown_worker():
    from lagomorph.worker import _heartbeat_loop

    shutdown_event = asyncio.Event()
    storage = await Storage.create(DATABASE_URL)
    try:
        task = asyncio.create_task(_heartbeat_loop(storage, "nonexistent", shutdown_event))
        await asyncio.sleep(0.05)
        shutdown_event.set()
        await task
    finally:
        await storage.close()


async def test_run_worker_loop_processes_task(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)

    import lagomorph.worker as wmod

    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue("add", "test_worker_loop", "tests.test_execute", args=[1, 2])

        worker_task = asyncio.create_task(
            wmod.run_worker(database_url=DATABASE_URL, concurrency=2, poll_interval=0.05, task_timeout=10)
        )

        await asyncio.sleep(0.5)

        worker_task.cancel()
        await worker_task

        task = await storage.get_task(task_id)
        assert task is not None
        assert task["status"] == "completed"
    finally:
        await storage.close()
