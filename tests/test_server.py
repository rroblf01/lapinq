from __future__ import annotations

import uuid

import httpx
from lagomorph.server import create_app
from lagomorph.storage import Storage

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lagomorph_test"


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
            resp = await client.get("/dashboard")
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
            assert "# HELP lagomorph_tasks" in text
            assert "# TYPE lagomorph_tasks gauge" in text
            assert 'lagomorph_tasks{queue="q1",status="pending"} 1' in text
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
            resp = await client.get("/dashboard")
            assert resp.status_code == 200
    finally:
        await storage.close()


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
