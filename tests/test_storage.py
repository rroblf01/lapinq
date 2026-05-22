from __future__ import annotations

import uuid

from lagomorph.storage import Storage

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lagomorph_test"


async def make_storage() -> Storage:
    return await Storage.create(DATABASE_URL)


async def test_enqueue_and_claim():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue(
            task_name="test_task",
            queue_name="default",
            module_path="tests.test_storage",
            args=[1, 2],
            kwargs={"key": "value"},
        )
        assert isinstance(task_id, uuid.UUID)

        claimed = await storage.claim_task("worker-1")
        assert claimed is not None
        assert claimed["id"] == task_id
        assert claimed["status"] == "running"
        assert claimed["worker_id"] == "worker-1"
        assert claimed["args"] == [1, 2]
        assert claimed["kwargs"] == {"key": "value"}
    finally:
        await storage.close()


async def test_claim_empty_queue():
    storage = await make_storage()
    try:
        claimed = await storage.claim_task("worker-1")
        assert claimed is None
    finally:
        await storage.close()


async def test_complete_stores_result():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("to_complete", "default", "test_module")
        await storage.claim_task("worker-1")
        await storage.complete_task(task_id, result='"ok"')
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["status"] == "completed"
        assert task["result"] == '"ok"'
    finally:
        await storage.close()


async def test_fail_exhausts_retries():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("to_fail", "default", "test_module", max_retries=0)
        await storage.claim_task("worker-1")
        await storage.fail_task(task_id, error="boom")
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["status"] == "failed"
        assert task["error"] == "boom"
    finally:
        await storage.close()


async def test_fail_retries_on_first_attempt():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("to_retry", "default", "test_module", max_retries=3)
        await storage.claim_task("worker-1")
        await storage.fail_task(task_id, error="transient")
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["status"] == "pending"
        assert task["attempts"] == 1
        assert task["error"] == "transient"
    finally:
        await storage.close()


async def test_list_tasks():
    storage = await make_storage()
    try:
        id1 = await storage.enqueue("task1", "q1", "m1")
        await storage.enqueue("task2", "q2", "m2")

        tasks = await storage.list_tasks()
        assert len(tasks) == 2

        q1_tasks = await storage.list_tasks(queue_name="q1")
        assert len(q1_tasks) == 1
        assert q1_tasks[0]["id"] == id1
    finally:
        await storage.close()


async def test_queue_stats():
    storage = await make_storage()
    try:
        await storage.enqueue("t1", "q1", "m1")
        await storage.enqueue("t2", "q1", "m1")
        await storage.enqueue("t3", "q2", "m2")

        stats = await storage.queue_stats()
        stats_map = {s["queue_name"]: s for s in stats}

        assert stats_map["q1"]["pending"] == 2
        assert stats_map["q2"]["pending"] == 1
    finally:
        await storage.close()


async def test_cancel_task():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("to_cancel", "q1", "m1")
        cancelled = await storage.cancel_task(task_id)
        assert cancelled is True
        task = await storage.get_task(task_id)
        assert task is None
    finally:
        await storage.close()


async def test_cancel_running_task_fails():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("running_task", "q1", "m1")
        await storage.claim_task("worker-1")
        cancelled = await storage.cancel_task(task_id)
        assert cancelled is False
    finally:
        await storage.close()


async def test_recover_stale_tasks():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("stale", "q1", "m1")
        await storage.claim_task("dead-worker")
        async with storage.pool.acquire() as conn:
            await conn.execute(
                "UPDATE lagomorph_tasks SET started_at = now() - interval '1 hour' WHERE id = $1",
                task_id,
            )
        recovered = await storage.recover_stale_tasks(max_running_seconds=300)
        assert task_id in recovered
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["status"] == "pending"
    finally:
        await storage.close()


async def test_retry_backoff_seconds():
    from lagomorph.storage import _retry_backoff_seconds
    assert _retry_backoff_seconds(0) == 0
    assert _retry_backoff_seconds(1) == 10
    assert _retry_backoff_seconds(2) == 30
    assert _retry_backoff_seconds(3) == 60
    assert _retry_backoff_seconds(10) == 600


async def test_skipped_locked_task():
    storage = await make_storage()
    try:
        id1 = await storage.enqueue("t1", "q1", "m1")
        await storage.enqueue("t2", "q1", "m1")

        async with storage.pool.acquire() as conn:
            await conn.execute("UPDATE lagomorph_tasks SET status = 'running' WHERE id = $1", id1)

        claimed = await storage.claim_task("worker-1", statuses=("pending",))
        assert claimed is not None
        assert claimed["id"] != id1
    finally:
        await storage.close()
