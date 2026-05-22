from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

import httpx


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
        name: str | None = None,
        queue_name: str | None = None,
        scheduled_at: str | None = None,
        max_retries: int | None = None,
        priority: int = 0,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            task_name = name if name is not None else func.__name__  # ty: ignore
            module = inspect.getmodule(func)
            if module is None:
                qualified_name = func.__qualname__  # ty: ignore
                module_path = func.__module__
            else:
                qualified_name = f"{module.__name__}.{func.__qualname__}"  # ty: ignore
                module_path = module.__name__
            self._registry[task_name] = qualified_name

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> httpx.Response:
                q = queue_name if queue_name is not None else self.queue_name
                payload: dict[str, Any] = {
                    "task_name": task_name,
                    "queue_name": q,
                    "args": list(args),
                    "kwargs": kwargs,
                    "module_path": module_path,
                }
                if scheduled_at is not None:
                    payload["scheduled_at"] = scheduled_at
                if max_retries is not None:
                    payload["max_retries"] = max_retries
                payload["priority"] = priority
                return self._client.post(
                    f"{self.server_url}/api/enqueue",
                    json=payload,
                )

            return wrapper

        return decorator

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
        name: str | None = None,
        queue_name: str | None = None,
        scheduled_at: str | None = None,
        max_retries: int | None = None,
        priority: int = 0,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            task_name = name if name is not None else func.__name__  # type: ignore
            module = inspect.getmodule(func)
            module_path = func.__module__ if module is None else module.__name__
            self._registry[task_name] = f"{module_path}.{func.__qualname__}"  # type: ignore

            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> httpx.Response:
                q = queue_name if queue_name is not None else self.queue_name
                payload: dict[str, Any] = {
                    "task_name": task_name,
                    "queue_name": q,
                    "args": list(args),
                    "kwargs": kwargs,
                    "module_path": module_path,
                }
                if scheduled_at is not None:
                    payload["scheduled_at"] = scheduled_at
                if max_retries is not None:
                    payload["max_retries"] = max_retries
                payload["priority"] = priority
                return await self._client.post(
                    f"{self.server_url}/api/enqueue",
                    json=payload,
                )

            return wrapper

        return decorator

    async def close(self) -> None:
        await self._client.aclose()
