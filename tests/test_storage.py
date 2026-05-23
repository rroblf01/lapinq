from __future__ import annotations

import uuid

import pytest
from lapinq.storage import Storage

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lapinq_test"


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
        assert task_id is not None
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
        assert task_id is not None
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
        assert task_id is not None
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
        assert id1 is not None
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
        assert task_id is not None
        cancelled = await storage.cancel_task(task_id)
        assert cancelled is True
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["status"] == "cancelled"
    finally:
        await storage.close()


async def test_cancel_running_task_fails():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("running_task", "q1", "m1")
        assert task_id is not None
        await storage.claim_task("worker-1")
        cancelled = await storage.cancel_task(task_id)
        assert cancelled is False
    finally:
        await storage.close()


async def test_recover_stale_tasks():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("stale", "q1", "m1")
        assert task_id is not None
        await storage.claim_task("dead-worker")
        async with storage.pool.acquire() as conn:
            await conn.execute(
                "UPDATE lapinq_tasks SET started_at = now() - interval '1 hour' WHERE id = $1",
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
    from lapinq.storage import _retry_backoff_seconds
    assert _retry_backoff_seconds(0) == 0
    assert _retry_backoff_seconds(1) == 10
    assert _retry_backoff_seconds(2) == 30
    assert _retry_backoff_seconds(3) == 60
    assert _retry_backoff_seconds(10) == 600


async def test_skipped_locked_task():
    storage = await make_storage()
    try:
        id1 = await storage.enqueue("t1", "q1", "m1")
        assert id1 is not None
        await storage.enqueue("t2", "q1", "m1")

        async with storage.pool.acquire() as conn:
            await conn.execute("UPDATE lapinq_tasks SET status = 'running' WHERE id = $1", id1)

        claimed = await storage.claim_task("worker-1", statuses=("pending",))
        assert claimed is not None
        assert claimed["id"] != id1
    finally:
        await storage.close()


async def test_list_failed_tasks():
    storage = await make_storage()
    try:
        t1 = await storage.enqueue("f1", "q1", "m1", max_retries=0)
        assert t1 is not None
        t2 = await storage.enqueue("f2", "q1", "m1", max_retries=0)
        assert t2 is not None
        t3 = await storage.enqueue("ok", "q1", "m1")
        assert t3 is not None
        await storage.claim_task("w1")
        await storage.fail_task(t1, error="err1")
        await storage.claim_task("w1")
        await storage.fail_task(t2, error="err2")
        failed = await storage.list_failed_tasks()
        ids = {t["id"] for t in failed}
        assert t1 in ids
        assert t2 in ids
        assert t3 not in ids
    finally:
        await storage.close()


async def test_requeue_task():
    storage = await make_storage()
    try:
        t1 = await storage.enqueue("rq1", "q1", "m1", max_retries=0)
        assert t1 is not None
        await storage.claim_task("w1")
        await storage.fail_task(t1, error="nope")
        ok = await storage.requeue_task(t1)
        assert ok is True
        task = await storage.get_task(t1)
        assert task is not None
        assert task["status"] == "pending"
        assert task["attempts"] == 0
        assert task["error"] is None
        ok = await storage.requeue_task(t1)
        assert ok is False
    finally:
        await storage.close()


async def test_fail_task_nonexistent():
    storage = await make_storage()
    try:
        await storage.fail_task(uuid.uuid4(), error="nope")
    finally:
        await storage.close()


async def test_heartbeat():
    storage = await make_storage()
    try:
        t1 = await storage.enqueue("hb1", "q1", "m1")
        assert t1 is not None
        await storage.claim_task("w1")
        task_before = await storage.get_task(t1)
        assert task_before is not None
        assert task_before["last_heartbeat"] is not None
        await storage.heartbeat("w1")
        task_after = await storage.get_task(t1)
        assert task_after is not None
        assert task_after["last_heartbeat"] >= task_before["last_heartbeat"]
    finally:
        await storage.close()


async def test_priority_ordering():
    storage = await make_storage()
    try:
        low = await storage.enqueue("low", "q1", "m1", priority=0)
        assert low is not None
        high = await storage.enqueue("high", "q1", "m1", priority=10)
        assert high is not None
        t1 = await storage.claim_task("w1")
        assert t1 is not None
        assert t1["id"] == high
        t2 = await storage.claim_task("w1")
        assert t2 is not None
        assert t2["id"] == low
    finally:
        await storage.close()


async def test_scheduled_at_delays_claim():
    storage = await make_storage()
    try:
        from datetime import datetime, timedelta, timezone

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        task_id = await storage.enqueue("delayed", "q1", "m1", scheduled_at=future)
        assert task_id is not None
        claimed = await storage.claim_task("w1")
        assert claimed is None
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        await storage.enqueue("immediate", "q1", "m1", scheduled_at=past)
        claimed = await storage.claim_task("w1")
        assert claimed is not None
        assert claimed["id"] != task_id
    finally:
        await storage.close()


async def test_enqueue_with_max_retries():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("retry5", "q1", "m1", max_retries=5)
        assert task_id is not None
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["max_retries"] == 5
    finally:
        await storage.close()


async def test_enqueue_with_ttl():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("ttl_task", "q1", "m1", ttl_seconds=3600)
        assert task_id is not None
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["ttl_seconds"] == 3600
    finally:
        await storage.close()


async def test_enqueue_ttl_zero_returns_none():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("volatile", "q1", "m1", ttl_seconds=0)
        assert task_id is None
    finally:
        await storage.close()


@pytest.mark.slow
async def test_cleanup_expired_tasks():
    import asyncio

    storage = await make_storage()
    try:
        tid1 = await storage.enqueue("exp1", "q1", "m1", ttl_seconds=0)
        tid2 = await storage.enqueue("keep", "q1", "m1")
        assert tid2 is not None
        tid3 = await storage.enqueue("exp3", "q1", "m1", ttl_seconds=3600)
        assert tid3 is not None
        assert tid1 is None

        tid_exp = await storage.enqueue("exp_soon", "q1", "m1", ttl_seconds=0.3)
        assert tid_exp is not None

        await asyncio.sleep(0.4)

        count = await storage.cleanup_expired_tasks()
        assert count >= 1

        after = await storage.get_task(tid_exp)
        assert after is not None
        assert after["status"] == "expired"

        kept = await storage.get_task(tid2)
        assert kept is not None
        assert await storage.get_task(tid3) is not None
    finally:
        await storage.close()


async def test_cleanup_no_expired_tasks():
    storage = await make_storage()
    try:
        await storage.enqueue("perm1", "q1", "m1")
        await storage.enqueue("perm2", "q2", "m2", ttl_seconds=None)
        count = await storage.cleanup_expired_tasks()
        assert count == 0
    finally:
        await storage.close()


async def test_list_tasks_with_status_filter():
    storage = await make_storage()
    try:
        await storage.enqueue("a", "q1", "m1")
        tid2 = await storage.enqueue("b", "q1", "m1")
        assert tid2 is not None
        await storage.complete_task(tid2)

        pending = await storage.list_tasks(status="pending")
        completed = await storage.list_tasks(status="completed")

        assert len(pending) == 1
        assert pending[0]["task_name"] == "a"
        assert len(completed) == 1
        assert completed[0]["task_name"] == "b"
    finally:
        await storage.close()


async def test_list_tasks_with_queue_and_status():
    storage = await make_storage()
    try:
        tid = await storage.enqueue("only_q2", "q2", "m1")
        assert tid is not None
        await storage.enqueue("q1_pending", "q1", "m1")
        await storage.complete_task(tid)

        result = await storage.list_tasks(queue_name="q2", status="completed")
        assert len(result) == 1
        assert result[0]["task_name"] == "only_q2"

        result2 = await storage.list_tasks(queue_name="q1", status="completed")
        assert len(result2) == 0
    finally:
        await storage.close()


async def test_list_tasks_with_limit():
    storage = await make_storage()
    try:
        for i in range(5):
            await storage.enqueue(f"t{i}", "q1", "m1")
        all_tasks = await storage.list_tasks(limit=10)
        limited = await storage.list_tasks(limit=2)
        assert len(all_tasks) == 5
        assert len(limited) == 2
    finally:
        await storage.close()
