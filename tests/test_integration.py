from __future__ import annotations

import asyncio
import uuid

from lagomorph.server import create_app
from lagomorph.storage import Storage
from lagomorph.client import TaskQueue


async def test_full_flow_enqueue_and_server_storage():
    storage = await Storage.create(
        "postgresql://postgres:test@localhost:5432/lagomorph_test"
    )
    app = create_app(database_url="postgresql://postgres:test@localhost:5432/lagomorph_test")
    app.state.storage = storage

    import httpx
    try:
        async with httpx.ASGITransport(app=app) as transport:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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
    storage = await Storage.create(
        "postgresql://postgres:test@localhost:5432/lagomorph_test"
    )
    try:
        task_id = await storage.enqueue(
            "my_task", "default", "app.tasks",
            args=[1], kwargs={"name": "test"},
        )

        claimed = await storage.claim_task("worker-42")
        assert claimed is not None
        assert claimed["id"] == task_id
        assert claimed["status"] == "running"
        assert claimed["args"] == [1]
        assert claimed["kwargs"] == {"name": "test"}

        await storage.complete_task(task_id)

        deleted = await storage.get_task(task_id)
        assert deleted is None
    finally:
        await storage.close()


async def test_full_flow_client_to_server():
    storage = await Storage.create(
        "postgresql://postgres:test@localhost:5432/lagomorph_test"
    )
    app = create_app(database_url="postgresql://postgres:test@localhost:5432/lagomorph_test")
    app.state.storage = storage

    import httpx
    try:
        async with httpx.ASGITransport(app=app) as transport:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                tq = TaskQueue(server_url="http://test", queue_name="integration")

                with mock.patch.object(tq, "_client") as mock_http_client:
                    mock_post = mock.MagicMock()
                    mock_http_client.post = mock_post
                    mock_post.return_value = httpx.Response(201, json={"task_id": str(uuid.uuid4())})

                    @tq.task(name="integration_task")
                    def integration_task(x: int) -> None:
                        pass

                    resp = integration_task(99)
                    assert resp.status_code == 201
                    assert "task_id" in resp.json()
    finally:
        await storage.close()


from unittest import mock
