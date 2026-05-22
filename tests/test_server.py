from __future__ import annotations

import asyncio
import uuid

import httpx
from lapinq.server import create_app
from lapinq.storage import Storage

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lapinq_test"


async def test_health():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["database"] == "connected"
    finally:
        await storage.close()


async def test_enqueue_endpoint():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            payload = {
                "task_name": "process_video",
                "queue_name": "video",
                "module_path": "app.tasks",
                "args": [1],
                "kwargs": {"codec": "h264"},
            }
            resp = await client.post("/api/enqueue", json=payload)
            assert resp.status_code == 201
            data = resp.json()
            assert "task_id" in data
            uuid.UUID(data["task_id"])
    finally:
        await storage.close()


async def test_enqueue_missing_task_name():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post("/api/enqueue", json={"queue_name": "test"})
            assert resp.status_code == 400
            assert "task_name" in resp.json()["error"]
    finally:
        await storage.close()


async def test_list_tasks():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            await client.post(
                "/api/enqueue",
                json={"task_name": "task1", "queue_name": "q1", "module_path": "m1"},
            )
            await client.post(
                "/api/enqueue",
                json={"task_name": "task2", "queue_name": "q1", "module_path": "m1"},
            )

            resp = await client.get("/api/tasks")
            assert resp.status_code == 200
            tasks = resp.json()
            assert len(tasks) == 2
    finally:
        await storage.close()


async def test_get_task():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            create_resp = await client.post(
                "/api/enqueue",
                json={"task_name": "get_me", "queue_name": "q1", "module_path": "m1"},
            )
            task_id = create_resp.json()["task_id"]

            resp = await client.get(f"/api/tasks/{task_id}")
            assert resp.status_code == 200
            assert resp.json()["task_name"] == "get_me"
    finally:
        await storage.close()


async def test_get_task_not_found():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get(f"/api/tasks/{uuid.uuid4()}")
            assert resp.status_code == 404
    finally:
        await storage.close()


async def test_invalid_uuid():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get("/api/tasks/not-a-uuid")
            assert resp.status_code == 400
    finally:
        await storage.close()


async def test_cancel_task():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            create_resp = await client.post(
                "/api/enqueue",
                json={"task_name": "cancel_me", "queue_name": "q1", "module_path": "m1"},
            )
            task_id = create_resp.json()["task_id"]

            resp = await client.delete(f"/api/tasks/{task_id}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "cancelled"
    finally:
        await storage.close()


async def test_cancel_nonexistent_task():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.delete(f"/api/tasks/{uuid.uuid4()}")
            assert resp.status_code == 404
    finally:
        await storage.close()


async def test_queue_stats():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            await client.post(
                "/api/enqueue",
                json={"task_name": "t1", "queue_name": "q1", "module_path": "m1"},
            )
            await client.post(
                "/api/enqueue",
                json={"task_name": "t2", "queue_name": "q1", "module_path": "m1"},
            )

            resp = await client.get("/api/queues")
            assert resp.status_code == 200
            stats = resp.json()
            q1_stats = [s for s in stats if s["queue_name"] == "q1"]
            assert len(q1_stats) == 1
            assert q1_stats[0]["pending"] == 2
    finally:
        await storage.close()


async def test_dashboard_page():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "Lagomorph Dashboard" in resp.text
    finally:
        await storage.close()


async def test_metrics_endpoint():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            await client.post(
                "/api/enqueue",
                json={"task_name": "t1", "queue_name": "q1", "module_path": "m1"},
            )
            resp = await client.get("/metrics")
            assert resp.status_code == 200
            text = resp.text
            assert "# HELP lapinq_tasks" in text
            assert "# TYPE lapinq_tasks gauge" in text
            assert 'lapinq_tasks{queue="q1",status="pending"} 1' in text
    finally:
        await storage.close()


async def test_auth_middleware_blocks_without_key():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL, api_key="secret-42")
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get("/api/queues")
            assert resp.status_code == 401
            assert resp.json()["error"] == "unauthorized"
    finally:
        await storage.close()


async def test_auth_middleware_allows_valid_key():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL, api_key="secret-42")
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get("/api/queues", headers={"X-API-Key": "secret-42"})
            assert resp.status_code == 200
    finally:
        await storage.close()


async def test_auth_middleware_skips_health():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL, api_key="secret-42")
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get("/health")
            assert resp.status_code == 200
    finally:
        await storage.close()


async def test_auth_middleware_skips_dashboard():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL, api_key="secret-42")
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get("/")
            assert resp.status_code == 200
    finally:
        await storage.close()


async def test_requeue_not_found():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(f"/api/tasks/{uuid.uuid4()}/requeue", json={})
            assert resp.status_code == 404
    finally:
        await storage.close()


async def test_requeue_not_failed():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/enqueue",
                json={"task_name": "r2", "queue_name": "q1", "module_path": "m1"},
            )
            task_id = resp.json()["task_id"]
            resp = await client.post(f"/api/tasks/{task_id}/requeue", json={})
            assert resp.status_code == 404
    finally:
        await storage.close()


async def test_auth_does_not_block_options():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL, api_key="secret-42")
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.options("/api/queues")
            assert resp.status_code == 405
    finally:
        await storage.close()


async def test_cors_preflight_with_auth():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL, api_key="secret-42")
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            headers = {
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            }
            resp = await client.options("/api/queues", headers=headers)
            assert resp.status_code == 200
    finally:
        await storage.close()


async def test_websocket_sends_stats_and_tasks():
    from starlette.testclient import TestClient

    app = create_app(database_url=DATABASE_URL)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "cards" in data
        assert "table" in data


async def test_rate_limiting_blocks_excess():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL, rate_limit=3)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            for _ in range(3):
                r = await client.get("/api/queues")
                assert r.status_code == 200
            r = await client.get("/api/queues")
            assert r.status_code == 429
            assert r.json()["error"] == "rate limit exceeded"
    finally:
        await storage.close()


async def test_enqueue_with_scheduled_at():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            payload = {
                "task_name": "delayed",
                "queue_name": "q1",
                "module_path": "m1",
                "scheduled_at": "2099-06-15T12:30:00+00:00",
            }
            resp = await client.post("/api/enqueue", json=payload)
            assert resp.status_code == 201
            resp2 = await client.get("/api/tasks")
            tasks = resp2.json()
            assert "2099-06-15T12:30:00" in tasks[0]["scheduled_at"]
    finally:
        await storage.close()


async def test_enqueue_invalid_scheduled_at():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            payload = {
                "task_name": "bad",
                "queue_name": "q1",
                "module_path": "m1",
                "scheduled_at": "not-a-date",
            }
            resp = await client.post("/api/enqueue", json=payload)
            assert resp.status_code == 400
            assert "scheduled_at" in resp.json()["error"]
    finally:
        await storage.close()


async def test_list_failed_tasks_endpoint():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/enqueue",
                json={"task_name": "f1", "queue_name": "q1", "module_path": "m1", "max_retries": 0},
            )
            task_id = uuid.UUID(resp.json()["task_id"])
            await storage.claim_task("test-w1")
            await storage.fail_task(task_id, error="boom")
            resp2 = await client.get("/api/tasks/failed")
            assert resp2.status_code == 200
            ids = {t["id"] for t in resp2.json()}
            assert str(task_id) in ids
    finally:
        await storage.close()


async def test_create_app_with_worker_flag():
    app = create_app(database_url=DATABASE_URL, worker=True)
    assert app is not None


async def test_inline_worker_processes_through_server():
    from starlette.testclient import TestClient

    app = create_app(database_url=DATABASE_URL, worker=True, worker_poll_interval=0.05)
    with TestClient(app) as client:
        resp = client.post(
            "/api/enqueue",
            json={
                "task_name": "add",
                "queue_name": "test_inline_srv",
                "module_path": "tests.test_execute",
                "args": [5, 7],
                "max_retries": 0,
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["task_id"]

        await asyncio.sleep(0.5)

        resp2 = client.get(f"/api/tasks/{task_id}")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "completed"


async def test_requeue_endpoint():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/enqueue",
                json={"task_name": "r1", "queue_name": "q2", "module_path": "m1", "max_retries": 0},
            )
            task_id = uuid.UUID(resp.json()["task_id"])
            await storage.claim_task("test-w2")
            await storage.fail_task(task_id, error="boom")
            resp2 = await client.post(f"/api/tasks/{task_id}/requeue", json={})
            assert resp2.status_code == 200
            assert resp2.json()["status"] == "requeued"
    finally:
        await storage.close()


async def test_enqueue_with_ttl_seconds():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/enqueue",
                json={"task_name": "ttl_task", "queue_name": "q1", "module_path": "m1", "ttl_seconds": 7200},
            )
            assert resp.status_code == 201
            task_id = uuid.UUID(resp.json()["task_id"])
            task = await storage.get_task(task_id)
            assert task is not None
            assert task["ttl_seconds"] == 7200
    finally:
        await storage.close()


async def test_enqueue_ttl_zero():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/enqueue",
                json={"task_name": "volatile", "queue_name": "q1", "module_path": "m1", "ttl_seconds": 0},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["task_id"] is None
            assert data["ttl_seconds"] == 0
    finally:
        await storage.close()


async def test_enqueue_invalid_ttl():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post(
                "/api/enqueue",
                json={"task_name": "bad_ttl", "queue_name": "q1", "module_path": "m1", "ttl_seconds": "not-a-number"},
            )
            assert resp.status_code == 400
            assert "ttl_seconds" in resp.json()["error"]
    finally:
        await storage.close()


async def test_requeue_invalid_uuid():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.post("/api/tasks/not-a-uuid/requeue", json={})
            assert resp.status_code == 400
    finally:
        await storage.close()


async def test_list_tasks_with_status():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            await client.post(
                "/api/enqueue",
                json={"task_name": "t1", "queue_name": "q1", "module_path": "m1"},
            )
            t2 = await storage.enqueue("t2", "q1", "m1")
            assert t2 is not None
            await storage.complete_task(t2)

            resp = await client.get("/api/tasks?status=pending")
            assert resp.status_code == 200
            names = [t["task_name"] for t in resp.json()]
            assert "t1" in names
            assert "t2" not in names

            resp2 = await client.get("/api/tasks?status=completed")
            names2 = [t["task_name"] for t in resp2.json()]
            assert "t2" in names2
    finally:
        await storage.close()


async def test_list_failed_tasks_with_queue_filter():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            t1 = await storage.enqueue("f1", "qa", "m1", max_retries=0)
            assert t1 is not None
            t2 = await storage.enqueue("f2", "qb", "m1", max_retries=0)
            assert t2 is not None
            await storage.claim_task("w1", statuses=("pending",))
            for tid in (t1, t2):
                await storage.fail_task(tid, error="err")

            resp = await client.get("/api/tasks/failed?queue=qa")
            assert resp.status_code == 200
            assert len(resp.json()) == 1
            assert resp.json()[0]["task_name"] == "f1"
    finally:
        await storage.close()


async def test_websocket_queue_filter():
    from starlette.testclient import TestClient

    app = create_app(database_url=DATABASE_URL)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "cards" in data
        assert "table" in data

        ws.send_json({"queue": "nonexistent"})
        data2 = ws.receive_json()
        assert data2 is not None


async def test_metrics_with_multiple_queues():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            await client.post(
                "/api/enqueue",
                json={"task_name": "m1", "queue_name": "qa", "module_path": "mp"},
            )
            await client.post(
                "/api/enqueue",
                json={"task_name": "m2", "queue_name": "qb", "module_path": "mp"},
            )
            resp = await client.get("/metrics")
            assert resp.status_code == 200
            assert 'queue="qa"' in resp.text
            assert 'queue="qb"' in resp.text
    finally:
        await storage.close()


async def test_websocket_id_filter_partial():
    from starlette.testclient import TestClient

    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage
    try:
        tid = await storage.enqueue("id_filter_test", "q1", "tests.test_execute")
        assert tid is not None
        with TestClient(app) as client, client.websocket_connect("/ws") as ws:
            ws.receive_json()
            prefix = str(tid)[:8]
            ws.send_json({"id": prefix})
            data = ws.receive_json()
            assert "id_filter_test" in data["table"]
    finally:
        await storage.close()
