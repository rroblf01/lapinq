from __future__ import annotations

import inspect
from typing import Any

import httpx


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
    return payload


def _resolve_module(func: Any) -> tuple[str, str]:
    module = inspect.getmodule(func)
    if module is None:
        return func.__qualname__, func.__module__
    return f"{module.__name__}.{func.__qualname__}", module.__name__


class TaskQueue:
    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8001",
        queue_name: str = "default",
        timeout: float = 30.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.queue_name = queue_name
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._registry: dict[str, str] = {}

    def task(
        self,
        name: Any = None,
        queue_name: str | None = None,
        scheduled_at: str | None = None,
        max_retries: int | None = None,
        priority: int = 0,
        ttl_seconds: float | None = None,
    ) -> Any:
        if callable(name):
            return self._register(name, None, self.queue_name, None, None, 0, None)

        def decorator(func: Any) -> Any:
            return self._register(func, name, queue_name, scheduled_at, max_retries, priority, ttl_seconds)

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
    ) -> Any:
        task_name = name if name is not None else func.__name__
        qualified_name, module_path = _resolve_module(func)
        self._registry[task_name] = qualified_name
        q = task_queue if task_queue is not None else self.queue_name

        def queue(*args: Any, **kwargs: Any) -> httpx.Response:
            payload = _build_payload(
                func, task_name, q, module_path, scheduled_at, max_retries, priority, ttl_seconds, args, kwargs,
            )
            return self._client.post(
                f"{self.server_url}/api/enqueue",
                json=payload,
            )

        func.queue = queue  # type: ignore[attr-defined]
        func.task_name = task_name  # type: ignore[attr-defined]
        return func

    def close(self) -> None:
        self._client.close()


class AsyncTaskQueue:
    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8001",
        queue_name: str = "default",
        timeout: float = 30.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.queue_name = queue_name
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        self._registry: dict[str, str] = {}

    def task(
        self,
        name: Any = None,
        queue_name: str | None = None,
        scheduled_at: str | None = None,
        max_retries: int | None = None,
        priority: int = 0,
        ttl_seconds: float | None = None,
    ) -> Any:
        if callable(name):
            return self._register(name, None, self.queue_name, None, None, 0, None)

        def decorator(func: Any) -> Any:
            return self._register(func, name, queue_name, scheduled_at, max_retries, priority, ttl_seconds)

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
    ) -> Any:
        task_name = name if name is not None else func.__name__
        qualified_name, module_path = _resolve_module(func)
        self._registry[task_name] = qualified_name
        q = task_queue if task_queue is not None else self.queue_name

        async def aqueue(*args: Any, **kwargs: Any) -> httpx.Response:
            payload = _build_payload(
                func, task_name, q, module_path, scheduled_at, max_retries, priority, ttl_seconds, args, kwargs,
            )
            return await self._client.post(
                f"{self.server_url}/api/enqueue",
                json=payload,
            )

        func.aqueue = aqueue  # type: ignore[attr-defined]
        func.task_name = task_name  # type: ignore[attr-defined]
        return func

    async def close(self) -> None:
        await self._client.aclose()
