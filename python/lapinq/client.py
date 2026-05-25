from __future__ import annotations

import inspect
import time
from typing import Any

import httpx


class TaskRef:
    """A reference to an enqueued task with result retrieval.

    Returned by .queue() and .aqueue() methods, wrapping the HTTP response
    and providing convenience methods to poll for results.
    """

    def __init__(self, response: httpx.Response, server_url: str, api_key: str | None, is_async: bool = False):
        self._response = response
        self._server_url = server_url
        self._api_key = api_key
        self._is_async = is_async
        self._task_id: str | None = None
        self._result: dict[str, Any] | None = None
        if response.status_code == 201:
            data = response.json()
            self._task_id = data.get("task_id")

    @property
    def task_id(self) -> str | None:
        return self._task_id

    @property
    def response(self) -> httpx.Response:
        return self._response

    def json(self) -> Any:
        return self._response.json()

    @property
    def status_code(self) -> int:
        return self._response.status_code

    def status(self) -> str | None:
        if self._result:
            return self._result.get("status")
        return None

    def _fetch_result(self) -> dict[str, Any] | None:
        if self._task_id is None:
            return None
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        resp = httpx.get(f"{self._server_url}/api/v1/tasks/{self._task_id}/result", headers=headers, timeout=10)
        if resp.status_code == 200:
            self._result = resp.json()
            return self._result
        return None

    async def _fetch_result_async(self) -> dict[str, Any] | None:
        if self._task_id is None:
            return None
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self._server_url}/api/v1/tasks/{self._task_id}/result", headers=headers)
        if resp.status_code == 200:
            self._result = resp.json()
            return self._result
        return None

    def wait(self, timeout: float = 30, poll_interval: float = 0.5) -> dict[str, Any]:
        """Poll until the task completes or timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self._fetch_result()
            if result and result.get("status") in ("completed", "failed", "cancelled", "expired"):
                return result
            time.sleep(poll_interval)
        raise TimeoutError(f"Task {self._task_id} did not finish within {timeout}s")

    async def awaitait(self, timeout: float = 30, poll_interval: float = 0.5) -> dict[str, Any]:
        """Async poll until the task completes or timeout expires."""
        import asyncio

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = await self._fetch_result_async()
            if result and result.get("status") in ("completed", "failed", "cancelled", "expired"):
                return result
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"Task {self._task_id} did not finish within {timeout}s")


def _build_payload(
    func: Any,
    task_name: str,
    queue_name: str,
    module_path: str,
    scheduled_at: str | None,
    max_retries: int | None,
    priority: int,
    ttl_seconds: float | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    retry_delay: float | None = None,
    retry_backoff: bool | None = None,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_name": task_name,
        "queue_name": queue_name,
        "args": list(args),
        "kwargs": kwargs,
        "module_path": module_path,
    }
    if scheduled_at is not None:
        payload["scheduled_at"] = scheduled_at
    if max_retries is not None:
        payload["max_retries"] = max_retries
    if ttl_seconds is not None:
        payload["ttl_seconds"] = ttl_seconds
    payload["priority"] = priority
    if metadata:
        payload["metadata"] = metadata
    if retry_delay is not None:
        payload["retry_delay"] = retry_delay
    if retry_backoff is not None:
        payload["retry_backoff"] = retry_backoff
    if webhook_url is not None:
        payload["webhook_url"] = webhook_url
    return payload


def _resolve_module(func: Any) -> tuple[str, str]:
    module = inspect.getmodule(func)
    if module is None:
        raise ValueError(
            f"Cannot resolve module for {func.__qualname__!r}. "
            "Ensure the function is defined in an importable module."
        )
    return f"{module.__name__}.{func.__qualname__}", module.__name__


def _headers(api_key: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if api_key is not None:
        headers["X-API-Key"] = api_key
    return headers


class TaskQueue:
    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8001",
        queue_name: str = "default",
        timeout: float = 30.0,
        api_key: str | None = None,
        default_ttl_seconds: float | None = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.queue_name = queue_name
        self.timeout = timeout
        self.api_key = api_key
        self.default_ttl_seconds = default_ttl_seconds
        self._client = httpx.Client(timeout=timeout)
        self._registry: dict[str, str] = {}

    def __enter__(self) -> TaskQueue:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def task(
        self,
        name: Any = None,
        queue_name: str | None = None,
        scheduled_at: str | None = None,
        max_retries: int | None = None,
        priority: int = 0,
        ttl_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
        retry_delay: float | None = None,
        retry_backoff: bool | None = None,
        webhook_url: str | None = None,
    ) -> Any:
        if callable(name):
            return self._register(name, None, self.queue_name, None, None, 0, None, None, None, None, None)

        def decorator(func: Any) -> Any:
            return self._register(
                func, name, queue_name, scheduled_at, max_retries, priority,
                ttl_seconds, metadata, retry_delay, retry_backoff, webhook_url,
            )

        return decorator

    def _register(
        self,
        func: Any,
        name: str | None,
        task_queue: str | None,
        scheduled_at: str | None,
        max_retries: int | None,
        priority: int,
        ttl_seconds: float | None,
        metadata: dict[str, Any] | None,
        retry_delay: float | None,
        retry_backoff: bool | None,
        webhook_url: str | None,
    ) -> Any:
        task_name = name if name is not None else func.__name__
        qualified_name, module_path = _resolve_module(func)
        self._registry[task_name] = qualified_name
        q = task_queue if task_queue is not None else self.queue_name
        effective_ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        def queue(*args: Any, **kwargs: Any) -> TaskRef:
            payload = _build_payload(
                func, task_name, q, module_path, scheduled_at, max_retries, priority, effective_ttl, args, kwargs,
                metadata=metadata, retry_delay=retry_delay, retry_backoff=retry_backoff, webhook_url=webhook_url,
            )
            resp = self._client.post(
                f"{self.server_url}/api/v1/enqueue",
                json=payload,
                headers=_headers(self.api_key),
            )
            return TaskRef(resp, self.server_url, self.api_key)

        func.queue = queue  # type: ignore[attr-defined]
        func.task_name = task_name  # type: ignore[attr-defined]
        return func

    def batch_enqueue(self, tasks: list[dict[str, Any]]) -> httpx.Response:
        """Enqueue multiple tasks in a single request."""
        return self._client.post(
            f"{self.server_url}/api/v1/enqueue/batch",
            json=tasks,
            headers=_headers(self.api_key),
        )

    def close(self) -> None:
        self._client.close()


class AsyncTaskQueue:
    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8001",
        queue_name: str = "default",
        timeout: float = 30.0,
        api_key: str | None = None,
        default_ttl_seconds: float | None = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.queue_name = queue_name
        self.timeout = timeout
        self.api_key = api_key
        self.default_ttl_seconds = default_ttl_seconds
        self._client = httpx.AsyncClient(timeout=timeout)
        self._registry: dict[str, str] = {}

    async def __aenter__(self) -> AsyncTaskQueue:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def task(
        self,
        name: Any = None,
        queue_name: str | None = None,
        scheduled_at: str | None = None,
        max_retries: int | None = None,
        priority: int = 0,
        ttl_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
        retry_delay: float | None = None,
        retry_backoff: bool | None = None,
        webhook_url: str | None = None,
    ) -> Any:
        if callable(name):
            return self._register(name, None, self.queue_name, None, None, 0, None, None, None, None, None)

        def decorator(func: Any) -> Any:
            return self._register(
                func, name, queue_name, scheduled_at, max_retries, priority,
                ttl_seconds, metadata, retry_delay, retry_backoff, webhook_url,
            )

        return decorator

    def _register(
        self,
        func: Any,
        name: str | None,
        task_queue: str | None,
        scheduled_at: str | None,
        max_retries: int | None,
        priority: int,
        ttl_seconds: float | None,
        metadata: dict[str, Any] | None,
        retry_delay: float | None,
        retry_backoff: bool | None,
        webhook_url: str | None,
    ) -> Any:
        task_name = name if name is not None else func.__name__
        qualified_name, module_path = _resolve_module(func)
        self._registry[task_name] = qualified_name
        q = task_queue if task_queue is not None else self.queue_name
        effective_ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        async def aqueue(*args: Any, **kwargs: Any) -> TaskRef:
            payload = _build_payload(
                func, task_name, q, module_path, scheduled_at, max_retries, priority, effective_ttl, args, kwargs,
                metadata=metadata, retry_delay=retry_delay, retry_backoff=retry_backoff, webhook_url=webhook_url,
            )
            resp = await self._client.post(
                f"{self.server_url}/api/v1/enqueue",
                json=payload,
                headers=_headers(self.api_key),
            )
            return TaskRef(resp, self.server_url, self.api_key, is_async=True)

        func.aqueue = aqueue  # type: ignore[attr-defined]
        func.task_name = task_name  # type: ignore[attr-defined]
        return func

    async def batch_enqueue(self, tasks: list[dict[str, Any]]) -> httpx.Response:
        """Enqueue multiple tasks in a single request."""
        return await self._client.post(
            f"{self.server_url}/api/v1/enqueue/batch",
            json=tasks,
            headers=_headers(self.api_key),
        )

    async def close(self) -> None:
        await self._client.aclose()
