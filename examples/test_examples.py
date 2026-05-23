"""
End-to-end test for FastAPI and Django examples.
Starts the lapinq server with an inline worker programmatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_examples")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:test@localhost:5432/lapinq_test")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_direct_enqueue():
    """Enqueue a task directly via the API and verify completion."""
    from lapinq.server import create_app
    from starlette.testclient import TestClient

    app = create_app(
        database_url=DATABASE_URL,
        worker=True,
        worker_concurrency=2,
        worker_poll_interval=0.05,
        worker_timeout=30,
    )

    with TestClient(app) as client:
        # Enqueue a task
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "add",
                "queue_name": "test_direct",
                "module_path": "examples.fastapi_app",
                "args": [3, 7],
                "kwargs": {},
                "max_retries": 0,
            },
        )
        assert resp.status_code == 201, f"Enqueue failed: {resp.text}"
        task_id = resp.json()["task_id"]
        logger.info("Enqueued task: %s", task_id)

        # Poll until completed
        for _ in range(30):
            resp2 = client.get(f"/api/v1/tasks/{task_id}")
            assert resp2.status_code == 200
            data = resp2.json()
            if data["status"] == "completed":
                result = json.loads(data["result"])
                assert result == 10, f"Expected 10, got {result}"
                logger.info("✓ Direct enqueue: task %s = %s", task_id, result)
                return
            await asyncio.sleep(0.2)

        raise AssertionError(f"Task {task_id} did not complete")

    storage = app.state.storage
    await storage.close()


async def test_fastapi_example():
    """Test the FastAPI example end-to-end."""
    from lapinq.server import create_app
    from starlette.testclient import TestClient

    app = create_app(
        database_url=DATABASE_URL,
        worker=True,
        worker_concurrency=2,
        worker_poll_interval=0.05,
        worker_timeout=30,
    )

    with TestClient(app) as client:
        # Enqueue via FastAPI task
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "slow_square",
                "queue_name": "fastapi",
                "module_path": "examples.fastapi_app",
                "args": [5],
                "kwargs": {},
                "max_retries": 0,
            },
        )
        assert resp.status_code == 201, f"FastAPI enqueue failed: {resp.text}"
        task_id = resp.json()["task_id"]
        logger.info("FastAPI enqueued slow_square(5): %s", task_id)

        for _ in range(60):
            resp2 = client.get(f"/api/v1/tasks/{task_id}")
            assert resp2.status_code == 200
            data = resp2.json()
            if data["status"] == "completed":
                result = json.loads(data["result"])
                assert result == 25, f"Expected 25, got {result}"
                logger.info("✓ FastAPI slow_square(5) = %s", result)
                return
            await asyncio.sleep(0.2)

        raise AssertionError(f"FastAPI task {task_id} did not complete")

    await app.state.storage.close()


async def test_fastapi_async_task():
    """Test that async tasks work through the FastAPI example."""
    from lapinq.server import create_app
    from starlette.testclient import TestClient

    app = create_app(
        database_url=DATABASE_URL,
        worker=True,
        worker_concurrency=2,
        worker_poll_interval=0.05,
        worker_timeout=30,
    )

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "echo_message",
                "queue_name": "fastapi",
                "module_path": "examples.fastapi_app",
                "args": ["hello async"],
                "kwargs": {},
                "max_retries": 0,
            },
        )
        assert resp.status_code == 201, f"Enqueue failed: {resp.text}"
        task_id = resp.json()["task_id"]
        logger.info("Enqueued async echo_message: %s", task_id)

        for _ in range(30):
            resp2 = client.get(f"/api/v1/tasks/{task_id}")
            assert resp2.status_code == 200
            data = resp2.json()
            if data["status"] == "completed":
                result = json.loads(data["result"])
                assert result == "echo: hello async", f"Expected 'echo: hello async', got {result}"
                logger.info("✓ FastAPI async echo_message = '%s'", result)
                return
            await asyncio.sleep(0.2)

        raise AssertionError(f"Async task {task_id} did not complete")

    await app.state.storage.close()


async def test_django_example():
    """Test the Django example tasks."""
    from lapinq.server import create_app
    from starlette.testclient import TestClient

    app = create_app(
        database_url=DATABASE_URL,
        worker=True,
        worker_concurrency=2,
        worker_poll_interval=0.05,
        worker_timeout=30,
    )

    with TestClient(app) as client:
        # Test add task
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "add",
                "queue_name": "django",
                "module_path": "examples.django_tasks",
                "args": [10, 20],
                "kwargs": {},
                "max_retries": 0,
            },
        )
        assert resp.status_code == 201, f"Django add enqueue failed: {resp.text}"
        task_id = resp.json()["task_id"]
        logger.info("Django enqueued add(10, 20): %s", task_id)

        for _ in range(30):
            resp2 = client.get(f"/api/v1/tasks/{task_id}")
            assert resp2.status_code == 200
            data = resp2.json()
            if data["status"] == "completed":
                result = json.loads(data["result"])
                assert result == 30, f"Expected 30, got {result}"
                logger.info("✓ Django add(10, 20) = %s", result)
                break
            await asyncio.sleep(0.2)
        else:
            raise AssertionError(f"Django add task {task_id} did not complete")

        # Test hello task
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "hello",
                "queue_name": "django",
                "module_path": "examples.django_tasks",
                "args": ["World"],
                "kwargs": {"greeting": "Hi"},
                "max_retries": 0,
            },
        )
        assert resp.status_code == 201, f"Django hello enqueue failed: {resp.text}"
        task_id2 = resp.json()["task_id"]
        logger.info("Django enqueued hello('World', greeting='Hi'): %s", task_id2)

        for _ in range(30):
            resp2 = client.get(f"/api/v1/tasks/{task_id2}")
            assert resp2.status_code == 200
            data = resp2.json()
            if data["status"] == "completed":
                result = json.loads(data["result"])
                assert result == "Hi, World!", f"Expected 'Hi, World!', got {result}"
                logger.info("✓ Django hello('World') = '%s'", result)
                return
            await asyncio.sleep(0.2)

        raise AssertionError(f"Django hello task {task_id2} did not complete")

    await app.state.storage.close()


async def test_task_result_endpoint():
    """Test the GET /api/v1/tasks/{id}/result endpoint."""
    from lapinq.server import create_app
    from starlette.testclient import TestClient

    app = create_app(
        database_url=DATABASE_URL,
        worker=True,
        worker_concurrency=1,
        worker_poll_interval=0.05,
        worker_timeout=30,
    )

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "add",
                "queue_name": "test_result",
                "module_path": "examples.fastapi_app",
                "args": [100, 1],
                "kwargs": {},
                "max_retries": 0,
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["task_id"]

        for _ in range(30):
            resp2 = client.get(f"/api/v1/tasks/{task_id}/result")
            assert resp2.status_code == 200
            data = resp2.json()
            if data.get("status") == "completed":
                assert data["result"] is not None
                assert json.loads(data["result"]) == 101
                logger.info("✓ Task result endpoint: %s", data)
                return
            await asyncio.sleep(0.2)

        raise AssertionError(f"Task {task_id} did not complete for result test")

    await app.state.storage.close()


async def test_requeue_flow():
    """Test requeueing a failed task."""
    from lapinq.server import create_app
    from lapinq.storage import Storage
    from starlette.testclient import TestClient

    storage = await Storage.create(DATABASE_URL)
    app = create_app(database_url=DATABASE_URL, worker=False)
    app.state.storage = storage

    with TestClient(app) as client:
        # Task that will fail
        resp = client.post(
            "/api/v1/enqueue",
            json={
                "task_name": "fail_func",
                "queue_name": "test_requeue",
                "module_path": "tests.test_execute",
                "args": [],
                "kwargs": {},
                "max_retries": 0,
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["task_id"]

        # Manually claim and fail
        from uuid import UUID

        await storage.claim_task("test-w1")
        await storage.fail_task(UUID(task_id), error="intentional failure")

        task = await storage.get_task(UUID(task_id))
        assert task["status"] == "failed"

        # Requeue
        resp2 = client.post(f"/api/v1/tasks/{task_id}/requeue")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "requeued"

        task2 = await storage.get_task(UUID(task_id))
        assert task2["status"] == "pending"
        logger.info("✓ Requeue flow: task %s requeued successfully", task_id)

    await storage.close()


async def main():
    logger.info("=" * 50)
    logger.info("Testing Lapinq examples...")
    logger.info("=" * 50)

    await test_direct_enqueue()
    await test_fastapi_example()
    await test_fastapi_async_task()
    await test_django_example()
    await test_task_result_endpoint()
    await test_requeue_flow()

    logger.info("=" * 50)
    logger.info("All example tests passed! ✓")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
