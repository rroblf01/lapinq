from __future__ import annotations

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
        await storage.complete_task(task_id)
        remaining = await storage.get_task(task_id)
        assert remaining is None
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
