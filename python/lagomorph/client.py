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
                payload = {
                    "task_name": task_name,
                    "queue_name": q,
                    "args": list(args),
                    "kwargs": kwargs,
                    "module_path": module_path,
                }
                return self._client.post(
                    f"{self.server_url}/api/enqueue",
                    json=payload,
                )

            return wrapper

        return decorator

    def close(self) -> None:
        self._client.close()
