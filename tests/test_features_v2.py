from __future__ import annotations

import asyncio
import uuid
from unittest import mock

import httpx
import pytest
from lapinq.client import AsyncTaskQueue, TaskQueue, TaskRef
from lapinq.execute import RetryError
from lapinq.server import create_app
from lapinq.storage import Storage

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lapinq_test"


# ---------------------------------------------------------------------------
# Storage: metadata
# ---------------------------------------------------------------------------

async def make_storage() -> Storage:
    return await Storage.create(DATABASE_URL)


async def test_enqueue_with_metadata():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue(
            "meta_test", "q1", "m1",
            metadata={"user_id": 42, "env": "staging"},
        )
        assert task_id is not None
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["metadata"] == {"user_id": 42, "env": "staging"}
    finally:
        await storage.close()


async def test_enqueue_default_metadata():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("no_meta", "q1", "m1")
        assert task_id is not None
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["metadata"] == {}
    finally:
        await storage.close()


async def test_update_task_metadata():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("update_meta", "q1", "m1")
        assert task_id is not None
        await storage.update_task_metadata(task_id, {"key": "value"})
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["metadata"]["key"] == "value"
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Storage: configurable retry
# ---------------------------------------------------------------------------

async def test_enqueue_with_retry_delay():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("retry_delay_test", "q1", "m1", max_retries=5, retry_delay=60, retry_backoff=False)
        assert task_id is not None
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["retry_delay"] == 60
        assert task["retry_backoff"] is False

        await storage.claim_task("w1")
        await storage.fail_task(task_id, error="transient")
        task2 = await storage.get_task(task_id)
        assert task2 is not None
        assert task2["status"] == "pending"
        assert task2["attempts"] == 1
    finally:
        await storage.close()


async def test_enqueue_with_retry_backoff_true():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("backoff_test", "q1", "m1", max_retries=3)
        assert task_id is not None
        await storage.claim_task("w1")
        await storage.fail_task(task_id, error="err")
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["retry_backoff"] is True
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Storage: progress
# ---------------------------------------------------------------------------

async def test_update_progress():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue("progress_test", "q1", "m1")
        assert task_id is not None
        await storage.update_progress(task_id, 50.0, "halfway there")
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["progress"] == 50.0
        assert task["progress_message"] == "halfway there"
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Storage: webhook_url
# ---------------------------------------------------------------------------

async def test_enqueue_with_webhook():
    storage = await make_storage()
    try:
        task_id = await storage.enqueue(
            "webhook_test", "q1", "m1",
            webhook_url="https://example.com/hook",
        )
        assert task_id is not None
        task = await storage.get_task(task_id)
        assert task is not None
        assert task["webhook_url"] == "https://example.com/hook"
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Storage: batch enqueue
# ---------------------------------------------------------------------------

async def test_enqueue_batch():
    storage = await make_storage()
    try:
        tasks = [
            {"task_name": "batch_a", "queue_name": "bq", "module_path": "m1", "args": [1]},
            {"task_name": "batch_b", "queue_name": "bq", "module_path": "m1", "kwargs": {"x": 2}},
            {"task_name": "batch_c", "queue_name": "bq", "module_path": "m1"},
        ]
        ids = await storage.enqueue_batch(tasks)
        assert len(ids) == 3
        all_tasks = await storage.list_tasks(queue_name="bq")
        assert len(all_tasks) == 3
        names = {t["task_name"] for t in all_tasks}
        assert names == {"batch_a", "batch_b", "batch_c"}
    finally:
        await storage.close()


async def test_enqueue_batch_with_ttl_zero():
    storage = await make_storage()
    try:
        tasks = [
            {"task_name": "will_persist", "queue_name": "bq", "module_path": "m1"},
            {"task_name": "will_discard", "queue_name": "bq", "module_path": "m1", "ttl_seconds": 0},
        ]
        ids = await storage.enqueue_batch(tasks)
        assert len(ids) == 1
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Client: default_ttl_seconds
# ---------------------------------------------------------------------------

def test_task_queue_default_ttl():
    tq = TaskQueue(server_url="http://test:8001", default_ttl_seconds=3600)
    assert tq.default_ttl_seconds == 3600


def test_default_ttl_applied_to_task():
    tq = TaskQueue(server_url="http://test:8001", default_ttl_seconds=7200)
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "abc"})

        @tq.task(name="default_ttl_task")
        def my_func():
            pass

        ref = my_func.queue()
        assert ref.task_id == "abc"
        payload = mock_post.call_args[1]["json"]
        assert payload["ttl_seconds"] == 7200


def test_explicit_ttl_overrides_default():
    tq = TaskQueue(server_url="http://test:8001", default_ttl_seconds=7200)
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "x"})

        @tq.task(name="explicit_ttl", ttl_seconds=100)
        def my_func():
            pass

        my_func.queue()
        payload = mock_post.call_args[1]["json"]
        assert payload["ttl_seconds"] == 100


# ---------------------------------------------------------------------------
# Client: metadata
# ---------------------------------------------------------------------------

def test_task_with_metadata():
    tq = TaskQueue(server_url="http://test:8001")
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "1"})

        @tq.task(name="meta_task", metadata={"user": "alice", "prio": "high"})
        def my_func():
            pass

        my_func.queue()
        payload = mock_post.call_args[1]["json"]
        assert payload["metadata"] == {"user": "alice", "prio": "high"}


def test_task_without_metadata_omits_field():
    tq = TaskQueue(server_url="http://test:8001")
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "1"})

        @tq.task(name="no_meta")
        def my_func():
            pass

        my_func.queue()
        payload = mock_post.call_args[1]["json"]
        assert "metadata" not in payload


# ---------------------------------------------------------------------------
# Client: retry_delay and retry_backoff
# ---------------------------------------------------------------------------

def test_task_with_retry_config():
    tq = TaskQueue(server_url="http://test:8001")
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "1"})

        @tq.task(name="retry_cfg", retry_delay=30, retry_backoff=False)
        def my_func():
            pass

        my_func.queue()
        payload = mock_post.call_args[1]["json"]
        assert payload["retry_delay"] == 30
        assert payload["retry_backoff"] is False


# ---------------------------------------------------------------------------
# Client: webhook_url
# ---------------------------------------------------------------------------

def test_task_with_webhook():
    tq = TaskQueue(server_url="http://test:8001")
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "1"})

        @tq.task(name="hook_task", webhook_url="https://hooks.example.com/done")
        def my_func():
            pass

        my_func.queue()
        payload = mock_post.call_args[1]["json"]
        assert payload["webhook_url"] == "https://hooks.example.com/done"


# ---------------------------------------------------------------------------
# Client: TaskRef
# ---------------------------------------------------------------------------

def test_taskref_from_response():
    resp = httpx.Response(201, json={"task_id": "abc-123"})
    ref = TaskRef(resp, "http://test:8001", None)
    assert ref.task_id == "abc-123"


def test_taskref_task_id_none_on_ttl_zero():
    resp = httpx.Response(201, json={"task_id": None, "ttl_seconds": 0})
    ref = TaskRef(resp, "http://test:8001", None)
    assert ref.task_id is None


def test_taskref_wait_completed():
    tq = TaskQueue(server_url="http://test:8001")
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "abc-123"})

        @tq.task(name="wait_test")
        def my_func():
            pass

        ref = my_func.queue()
        assert ref.task_id == "abc-123"

        with mock.patch("lapinq.client.httpx.get") as mock_get:
            mock_get.return_value = httpx.Response(
                200,
                json={
                    "id": "abc-123",
                    "status": "completed",
                    "result": '"done"',
                    "error": None,
                    "completed_at": "2026-01-01T00:00:00",
                },
            )
            result = ref.wait(timeout=5)
            assert result["status"] == "completed"
            assert result["result"] == '"done"'


# ---------------------------------------------------------------------------
# Client: batch_enqueue
# ---------------------------------------------------------------------------

def test_batch_enqueue_sync():
    tq = TaskQueue(server_url="http://test:8001")
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_ids": ["a", "b"], "count": 2})

        tasks = [
            {"task_name": "t1", "queue_name": "q1", "module_path": "m1"},
            {"task_name": "t2", "queue_name": "q1", "module_path": "m1"},
        ]
        resp = tq.batch_enqueue(tasks)
        assert resp.status_code == 201
        assert resp.json()["count"] == 2
        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == "http://test:8001/api/v1/enqueue/batch"
        assert mock_post.call_args[1]["json"] == tasks


@pytest.mark.asyncio
async def test_batch_enqueue_async():
    atq = AsyncTaskQueue(server_url="http://test:8001")
    try:
        with mock.patch.object(atq._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(201, json={"task_ids": ["x"], "count": 1})

            tasks = [{"task_name": "t1", "queue_name": "q1", "module_path": "m1"}]
            resp = await atq.batch_enqueue(tasks)
            assert resp.status_code == 201
            assert resp.json()["count"] == 1
    finally:
        await atq.close()


# ---------------------------------------------------------------------------
# Client: async TaskRef
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_taskref_awaitait():
    atq = AsyncTaskQueue(server_url="http://test:8001")
    try:
        with mock.patch.object(atq._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(201, json={"task_id": "async-123"})

            @atq.task(name="async_wait")
            async def my_async():
                return "done"

            ref = await my_async.aqueue()
            assert ref.task_id == "async-123"

            with mock.patch("lapinq.client.httpx.AsyncClient.get") as mock_get:
                mock_resp = httpx.Response(
                    200,
                    json={
                        "id": "async-123",
                        "status": "completed",
                        "result": '"done"',
                        "error": None,
                        "completed_at": "2026-01-01T00:00:00",
                    },
                )
                mock_get.return_value = mock_resp

                result = await ref.awaitait(timeout=5)
                assert result["status"] == "completed"
    finally:
        await atq.close()


# ---------------------------------------------------------------------------
# Client: async with metadata / retry config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_task_with_metadata():
    atq = AsyncTaskQueue(server_url="http://test:8001")
    try:
        with mock.patch.object(atq._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(201, json={"task_id": "1"})

            @atq.task(name="async_meta", metadata={"source": "test"})
            async def my_async():
                pass

            await my_async.aqueue()
            payload = mock_post.call_args[1]["json"]
            assert payload["metadata"] == {"source": "test"}
    finally:
        await atq.close()


# ---------------------------------------------------------------------------
# Server: batch enqueue
# ---------------------------------------------------------------------------

async def test_server_batch_enqueue():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            tasks = [
                {"task_name": "srv_batch_a", "queue_name": "sbq", "module_path": "m1"},
                {"task_name": "srv_batch_b", "queue_name": "sbq", "module_path": "m1"},
            ]
            resp = await client.post("/api/v1/enqueue/batch", json=tasks)
            assert resp.status_code == 201
            data = resp.json()
            assert data["count"] == 2
            assert len(data["task_ids"]) == 2

            list_resp = await client.get("/api/v1/tasks?queue=sbq")
            assert len(list_resp.json()) == 2
    finally:
        await storage.close()


async def test_server_batch_enqueue_invalid_body():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post("/api/v1/enqueue/batch", json={"not": "array"})
            assert resp.status_code == 400
            assert "array" in resp.json()["error"]
    finally:
        await storage.close()


async def test_server_batch_enqueue_missing_task_name():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post("/api/v1/enqueue/batch", json=[{"queue_name": "q"}])
            assert resp.status_code == 400
            assert "task_name" in resp.json()["error"]
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Server: progress endpoint
# ---------------------------------------------------------------------------

async def test_server_update_progress():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            create_resp = await client.post(
                "/api/v1/enqueue",
                json={"task_name": "prog_test", "queue_name": "q1", "module_path": "m1"},
            )
            task_id = create_resp.json()["task_id"]

            resp = await client.patch(
                f"/api/v1/tasks/{task_id}/progress",
                json={"progress": 75, "message": "almost done"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            task = await storage.get_task(uuid.UUID(task_id))
            assert task is not None
            assert task["progress"] == 75.0
            assert task["progress_message"] == "almost done"
    finally:
        await storage.close()


async def test_server_update_progress_invalid():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            create_resp = await client.post(
                "/api/v1/enqueue",
                json={"task_name": "prog_inv", "queue_name": "q1", "module_path": "m1"},
            )
            task_id = create_resp.json()["task_id"]

            resp = await client.patch(
                f"/api/v1/tasks/{task_id}/progress",
                json={"progress": 999},
            )
            assert resp.status_code == 400
            assert "between 0 and 100" in resp.json()["error"]

            resp2 = await client.patch(
                f"/api/v1/tasks/{task_id}/progress",
                json={},
            )
            assert resp2.status_code == 400
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Server: enqueue with metadata
# ---------------------------------------------------------------------------

async def test_server_enqueue_with_metadata():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/v1/enqueue",
                json={
                    "task_name": "meta_srv",
                    "queue_name": "q1",
                    "module_path": "m1",
                    "metadata": {"env": "test", "version": 2},
                },
            )
            assert resp.status_code == 201
            task_id = uuid.UUID(resp.json()["task_id"])
            task = await storage.get_task(task_id)
            assert task is not None
            assert task["metadata"]["env"] == "test"
            assert task["metadata"]["version"] == 2
    finally:
        await storage.close()


async def test_server_enqueue_invalid_metadata():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/v1/enqueue",
                json={
                    "task_name": "bad_meta",
                    "queue_name": "q1",
                    "module_path": "m1",
                    "metadata": "not-an-object",
                },
            )
            assert resp.status_code == 400
            assert "metadata must be a JSON object" in resp.json()["error"]
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Server: enqueue with retry config
# ---------------------------------------------------------------------------

async def test_server_enqueue_with_retry_config():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/v1/enqueue",
                json={
                    "task_name": "retry_cfg_srv",
                    "queue_name": "q1",
                    "module_path": "m1",
                    "retry_delay": 30,
                    "retry_backoff": False,
                },
            )
            assert resp.status_code == 201
            task_id = uuid.UUID(resp.json()["task_id"])
            task = await storage.get_task(task_id)
            assert task is not None
            assert task["retry_delay"] == 30
            assert task["retry_backoff"] is False
    finally:
        await storage.close()


async def test_server_enqueue_with_webhook():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/v1/enqueue",
                json={
                    "task_name": "hook_srv",
                    "queue_name": "q1",
                    "module_path": "m1",
                    "webhook_url": "https://hooks.example.com/done",
                },
            )
            assert resp.status_code == 201
            task_id = uuid.UUID(resp.json()["task_id"])
            task = await storage.get_task(task_id)
            assert task is not None
            assert task["webhook_url"] == "https://hooks.example.com/done"
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Retry exception
# ---------------------------------------------------------------------------

def test_retry_exception_default():
    r = RetryError()
    assert r.countdown == 10
    assert r.message is None
    assert str(r) == "Retry in 10s"


def test_retry_exception_custom():
    r = RetryError(countdown=60, message="rate limited")
    assert r.countdown == 60
    assert r.message == "rate limited"


# ---------------------------------------------------------------------------
# Integration: inline worker processes task with progress
# ---------------------------------------------------------------------------

@pytest.mark.slow
async def test_inline_worker_with_metadata_and_progress():
    import asyncio

    # Register a task with metadata and external progress update
    from lapinq.client import TaskQueue
    from starlette.testclient import TestClient
    tq = TaskQueue(server_url="http://test:8001")

    @tq.task(name="prog_demo")
    def prog_demo(x: int) -> int:
        return x * 2

    app = create_app(database_url=DATABASE_URL, worker=True, worker_poll_interval=0.05)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "add",
                "queue_name": "test_feat_inline",
                "module_path": "tests.test_execute",
                "args": [5, 7],
                "max_retries": 0,
                "metadata": {"source": "integration"},
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["task_id"]

        await asyncio.sleep(0.5)

        resp2 = client.get(f"/api/v1/tasks/{task_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] == "completed"
        assert data["metadata"] == {"source": "integration"}


# ---------------------------------------------------------------------------
# Integration: batch enqueue end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.slow
async def test_batch_enqueue_e2e():
    import asyncio

    from starlette.testclient import TestClient

    app = create_app(database_url=DATABASE_URL, worker=True, worker_poll_interval=0.05)
    with TestClient(app) as client:
        tasks = [
            {
                "task_name": "add", "queue_name": "batch_e2e",
                "module_path": "tests.test_execute",
                "args": [1, 2], "max_retries": 0,
            },
            {
                "task_name": "add", "queue_name": "batch_e2e",
                "module_path": "tests.test_execute",
                "args": [3, 4], "max_retries": 0,
            },
        ]
        resp = client.post("/api/v1/enqueue/batch", json=tasks)
        assert resp.status_code == 201
        assert resp.json()["count"] == 2

        await asyncio.sleep(0.5)

        list_resp = client.get("/api/v1/tasks?queue=batch_e2e")
        tasks_data = list_resp.json()
        assert len(tasks_data) == 2
        for t in tasks_data:
            assert t["status"] == "completed"


# ---------------------------------------------------------------------------
# Integration: inline worker with retry_delay
# ---------------------------------------------------------------------------

@pytest.mark.slow
async def test_inline_worker_retry_delay():
    import asyncio

    from starlette.testclient import TestClient

    app = create_app(database_url=DATABASE_URL, worker=True, worker_poll_interval=0.05)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "fail_always",
                "queue_name": "retry_delay_test",
                "module_path": "tests.test_features_v2",
                "args": [],
                "max_retries": 2,
                "retry_delay": 0.05,
                "retry_backoff": False,
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["task_id"]

        await asyncio.sleep(0.3)

        resp2 = client.get(f"/api/v1/tasks/{task_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        # Task should have been retried and failed again
        assert data["status"] in ("pending", "failed")
        assert int(data.get("attempts", 0)) >= 1


def fail_always() -> int:
    raise RuntimeError("always fails")


# ---------------------------------------------------------------------------
# Scheduler / periodic tasks
# ---------------------------------------------------------------------------

class TestCronParsing:
    def test_cron_every_minute(self):
        from datetime import datetime, timezone

        from lapinq.scheduler import _parse_cron, _should_run
        cron = _parse_cron("* * * * *")
        dt = datetime(2026, 5, 25, 10, 30, tzinfo=timezone.utc)
        assert _should_run(cron, dt)

    def test_cron_specific_hour(self):
        from datetime import datetime, timezone

        from lapinq.scheduler import _parse_cron, _should_run
        cron = _parse_cron("0 14 * * *")
        dt = datetime(2026, 5, 25, 14, 0, tzinfo=timezone.utc)
        assert _should_run(cron, dt)
        dt2 = datetime(2026, 5, 25, 15, 0, tzinfo=timezone.utc)
        assert not _should_run(cron, dt2)

    def test_cron_range(self):
        from datetime import datetime, timezone

        from lapinq.scheduler import _parse_cron, _should_run
        cron = _parse_cron("30 9-17 * * 1-5")
        dt = datetime(2026, 5, 25, 9, 30, tzinfo=timezone.utc)  # Monday
        assert _should_run(cron, dt)
        dt2 = datetime(2026, 5, 30, 9, 30, tzinfo=timezone.utc)  # Saturday
        assert not _should_run(cron, dt2)

    def test_cron_step(self):
        from datetime import datetime, timezone

        from lapinq.scheduler import _parse_cron, _should_run
        cron = _parse_cron("*/15 * * * *")
        dt = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
        assert _should_run(cron, dt)
        dt2 = datetime(2026, 5, 25, 10, 7, tzinfo=timezone.utc)
        assert not _should_run(cron, dt2)
        dt3 = datetime(2026, 5, 25, 10, 15, tzinfo=timezone.utc)
        assert _should_run(cron, dt3)

    def test_cron_list(self):
        from datetime import datetime, timezone

        from lapinq.scheduler import _parse_cron, _should_run
        cron = _parse_cron("0,30 * * * *")
        dt = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
        assert _should_run(cron, dt)
        dt2 = datetime(2026, 5, 25, 10, 15, tzinfo=timezone.utc)
        assert not _should_run(cron, dt2)
        dt3 = datetime(2026, 5, 25, 10, 30, tzinfo=timezone.utc)
        assert _should_run(cron, dt3)

    def test_cron_invalid(self):
        import pytest
        from lapinq.scheduler import _parse_cron
        with pytest.raises(ValueError, match="expected 5 fields"):
            _parse_cron("invalid")

    def test_parse_cron_returns_sets(self):
        from lapinq.scheduler import _parse_cron
        result = _parse_cron("0 9 * * 1")
        minutes, hours, days, months, weekdays = result
        assert minutes == {0}
        assert hours == {9}
        # Cron weekday 1 (Mon) → Python weekday 0
        assert weekdays == {0}

    def test_cron_weekday_mapping(self):
        from datetime import datetime, timezone

        from lapinq.scheduler import _parse_cron, _should_run
        # Cron "0" = Sunday, Python "6" = Sunday
        cron = _parse_cron("* * * * 0")
        dt = datetime(2026, 5, 31, 10, 0, tzinfo=timezone.utc)  # Sunday
        assert _should_run(cron, dt)
        dt2 = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)  # Monday
        assert not _should_run(cron, dt2)

        # Cron "1" = Monday, Python "0" = Monday
        cron2 = _parse_cron("* * * * 1")
        dt3 = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)  # Monday
        assert _should_run(cron2, dt3)


@pytest.mark.asyncio
async def test_scheduler_tick_enqueues_task():
    from lapinq.scheduler import Scheduler

    storage = await Storage.create(DATABASE_URL)
    try:
        sched = Scheduler(storage, interval=9999)
        await sched._ensure_table()

        async with storage.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO lapinq_scheduled_tasks
                    (task_name, module_path, queue_name, cron, enabled)
                VALUES ($1, $2, $3, $4, TRUE)
                """,
                "scheduled_test", "tests.test_execute", "sched_q", "* * * * *",
            )

        await sched._tick()

        tasks = await storage.list_tasks(queue_name="sched_q")
        assert len(tasks) >= 1
        assert tasks[0]["task_name"] == "scheduled_test"
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_scheduler_skips_disabled():
    from lapinq.scheduler import Scheduler

    storage = await Storage.create(DATABASE_URL)
    try:
        sched = Scheduler(storage, interval=9999)
        await sched._ensure_table()

        async with storage.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO lapinq_scheduled_tasks
                    (task_name, module_path, queue_name, cron, enabled)
                VALUES ($1, $2, $3, $4, FALSE)
                """,
                "disabled_task", "m1", "sched_q2", "* * * * *",
            )

        await sched._tick()

        tasks = await storage.list_tasks(queue_name="sched_q2")
        assert len(tasks) == 0
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_scheduler_start_stop():
    from lapinq.scheduler import Scheduler

    storage = await Storage.create(DATABASE_URL)
    try:
        sched = Scheduler(storage, interval=0.05)
        await sched.start()
        await asyncio.sleep(0.1)
        await sched.stop()
    finally:
        await storage.close()
