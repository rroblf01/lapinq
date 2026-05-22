from __future__ import annotations

from unittest import mock

import httpx
import pytest
from lagomorph.client import AsyncTaskQueue, TaskQueue


@pytest.fixture
def task_queue():
    return TaskQueue(server_url="http://test:8001", queue_name="test_queue")


def test_task_queue_init():
    tq = TaskQueue(server_url="http://example:8001", queue_name="myqueue")
    assert tq.server_url == "http://example:8001"
    assert tq.queue_name == "myqueue"


def test_task_decorator_registers_function(task_queue):
    @task_queue.task(name="my_task")
    def my_func(x: int, y: str) -> str:
        return f"{x}-{y}"

    assert "my_task" in task_queue._registry
    assert "tests.test_client" in task_queue._registry["my_task"]


def test_task_decorator_uses_function_name(task_queue):
    @task_queue.task()
    def auto_named() -> None:
        pass

    assert "auto_named" in task_queue._registry


def test_task_decorator_no_parens(task_queue):
    @task_queue.task
    def no_parens() -> int:
        return 42

    assert "no_parens" in task_queue._registry
    assert no_parens() == 42


def test_task_decorator_custom_queue(task_queue):
    @task_queue.task(name="custom_q_task", queue_name="other_queue")
    def custom_q() -> None:
        pass

    assert "custom_q_task" in task_queue._registry


def test_original_function_still_callable(task_queue):
    @task_queue.task(name="add")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5
    assert add(a=10, b=20) == 30


def test_queue_sends_http_request(task_queue):
    with mock.patch.object(task_queue._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "abc-123"})

        @task_queue.task(name="send_me")
        def send_me(a: int, b: str = "default") -> None:
            pass

        resp = send_me.queue(42, b="hello")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "http://test:8001/api/enqueue"
        payload = call_kwargs[1]["json"]
        assert payload["task_name"] == "send_me"
        assert payload["queue_name"] == "test_queue"
        assert payload["args"] == [42]
        assert payload["kwargs"] == {"b": "hello"}
        assert resp.status_code == 201


def test_queue_default_queue():
    tq2 = TaskQueue(server_url="http://other:8001", queue_name="other_q")

    with mock.patch.object(tq2._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "xyz"})

        @tq2.task(name="use_default_q")
        def use_default_q() -> None:
            pass

        use_default_q.queue()

        payload = mock_post.call_args[1]["json"]
        assert payload["queue_name"] == "other_q"


def test_close_method(task_queue):
    with mock.patch.object(task_queue._client, "close") as mock_close:
        task_queue.close()
        mock_close.assert_called_once()


def test_multiple_tasks_different_queues():
    tq = TaskQueue(server_url="http://test:8001", queue_name="default")

    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "1"})

        @tq.task(name="task_a", queue_name="queue_a")
        def task_a() -> None:
            pass

        @tq.task(name="task_b", queue_name="queue_b")
        def task_b() -> None:
            pass

        task_a.queue()
        assert mock_post.call_args[1]["json"]["queue_name"] == "queue_a"

        task_b.queue()
        assert mock_post.call_args[1]["json"]["queue_name"] == "queue_b"


def test_task_decorator_with_scheduled_at():
    tq = TaskQueue(server_url="http://test:8001")
    with mock.patch.object(tq._client, "post") as mock_post:
        mock_post.return_value = httpx.Response(201, json={"task_id": "1"})

        @tq.task(name="scheduled", scheduled_at="2099-01-01T00:00:00", max_retries=5, priority=10)
        def scheduled() -> None:
            pass

        scheduled.queue()
        payload = mock_post.call_args[1]["json"]
        assert payload["scheduled_at"] == "2099-01-01T00:00:00"
        assert payload["max_retries"] == 5
        assert payload["priority"] == 10


@pytest.mark.asyncio
async def test_async_task_queue():
    atq = AsyncTaskQueue(server_url="http://test:8001", queue_name="async_q")
    try:
        with mock.patch.object(atq._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(201, json={"task_id": "async-42"})

            @atq.task(name="async_task")
            async def my_async() -> str:
                return "real result"

            resp = await my_async.aqueue()
            assert resp.json()["task_id"] == "async-42"
            payload = mock_post.call_args[1]["json"]
            assert payload["task_name"] == "async_task"
            assert payload["queue_name"] == "async_q"

            assert await my_async() == "real result"
    finally:
        await atq.close()


@pytest.mark.asyncio
async def test_async_task_no_parens():
    atq = AsyncTaskQueue(server_url="http://test:8001")
    try:
        with mock.patch.object(atq._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(201, json={"task_id": "1"})

            @atq.task
            async def no_parens() -> str:
                return "done"

            resp = await no_parens.aqueue()
            assert resp.json()["task_id"] == "1"

            assert await no_parens() == "done"
    finally:
        await atq.close()
