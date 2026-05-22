from __future__ import annotations

import uuid
from unittest import mock

import httpx
from lagomorph.client import TaskQueue
from lagomorph.server import create_app
from lagomorph.storage import Storage

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lagomorph_test"


async def test_full_flow_enqueue_and_server_storage():
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
                json={
                    "task_name": "process_video",
                    "queue_name": "video",
                    "module_path": "app.tasks",
                    "args": [42],
                    "kwargs": {"codec": "h264"},
                },
            )
            assert resp.status_code == 201
            task_id = uuid.UUID(resp.json()["task_id"])

            task = await storage.get_task(task_id)
            assert task is not None
            assert task["task_name"] == "process_video"
            assert task["queue_name"] == "video"
            assert task["module_path"] == "app.tasks"
            assert task["args"] == [42]
            assert task["kwargs"] == {"codec": "h264"}
            assert task["status"] == "pending"
    finally:
        await storage.close()


async def test_full_flow_claim_and_complete():
    storage = await Storage.create(DATABASE_URL)
    try:
        task_id = await storage.enqueue(
            "my_task",
            "default",
            "app.tasks",
            args=[1],
            kwargs={"name": "test"},
        )

        claimed = await storage.claim_task("worker-42")
        assert claimed is not None
        assert claimed["id"] == task_id
        assert claimed["status"] == "running"
        assert claimed["args"] == [1]
        assert claimed["kwargs"] == {"name": "test"}

        await storage.complete_task(task_id, result='"done"')

        completed = await storage.get_task(task_id)
        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["result"] == '"done"'
    finally:
        await storage.close()


async def test_full_flow_client_to_server():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage

    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as _client,
        ):
            tq = TaskQueue(server_url="http://test", queue_name="integration")

            with mock.patch.object(tq, "_client") as mock_http_client:
                mock_post = mock.MagicMock()
                mock_http_client.post = mock_post
                mock_post.return_value = httpx.Response(201, json={"task_id": str(uuid.uuid4())})

                @tq.task(name="integration_task")
                def integration_task(x: int) -> None:
                    pass

                resp = integration_task.queue(99)
                assert resp.status_code == 201
                assert "task_id" in resp.json()
    finally:
        await storage.close()


async def test_health_check_endpoint():
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


async def test_payload_too_large():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage

    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            big_args = ["x" * 1024 * 200]
            resp = await client.post(
                "/api/enqueue",
                json={
                    "task_name": "big",
                    "queue_name": "test",
                    "module_path": "app",
                    "args": big_args,
                },
            )
            assert resp.status_code == 413
    finally:
        await storage.close()


async def test_missing_module_path():
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
                json={"task_name": "no_module"},
            )
            assert resp.status_code == 400
            assert "module_path" in resp.json()["error"]
    finally:
        await storage.close()


async def test_queues_html_with_data():
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
                json={"task_name": "t1", "queue_name": "test_q", "module_path": "m1"},
            )
            resp = await client.get("/api/queues/html")
            assert resp.status_code == 200
            assert "test_q" in resp.text
            assert "pending" in resp.text
    finally:
        await storage.close()


async def test_tasks_html_with_data():
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
                json={"task_name": "my_task", "queue_name": "test_q", "module_path": "m1"},
            )
            resp = await client.get("/api/tasks/html?limit=20")
            assert resp.status_code == 200
            assert "my_task" in resp.text
            assert "test_q" in resp.text
    finally:
        await storage.close()


async def test_dashboard_html_endpoint():
    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL)
    app.state.storage = storage

    try:
        async with (
            httpx.ASGITransport(app=app) as transport,
            httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        ):
            resp = await client.get("/api/queues/html")
            assert resp.status_code == 200
            assert "text/html" in resp.headers["content-type"]

            resp2 = await client.get("/api/tasks/html")
            assert resp2.status_code == 200
            assert "text/html" in resp2.headers["content-type"]
    finally:
        await storage.close()
