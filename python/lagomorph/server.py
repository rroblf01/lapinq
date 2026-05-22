from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from lagomorph.dashboard import dashboard_page, queues_html, tasks_html
from lagomorph.storage import Storage

MAX_PAYLOAD_SIZE = 1024 * 100  # 100 KB


def create_app(database_url: str = "postgresql://localhost:5432/lagomorph") -> Starlette:
    routes = [
        Route("/api/enqueue", enqueue, methods=["POST"]),
        Route("/api/queues", queue_stats, methods=["GET"]),
        Route("/api/tasks/html", tasks_html_endpoint, methods=["GET"]),
        Route("/api/queues/html", queues_html_endpoint, methods=["GET"]),
        Route("/api/tasks", list_tasks, methods=["GET"]),
        Route("/api/tasks/{task_id:str}", get_task, methods=["GET"]),
        Route("/api/tasks/{task_id:str}", cancel_task, methods=["DELETE"]),
        Route("/dashboard", dashboard, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
    ]

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None]:
        storage = await Storage.create(database_url)
        app.state.storage = storage
        yield
        await storage.close()

    app = Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        ],
    )
    return app


async def enqueue(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage

    body = await request.json()
    if _estimate_size(body) > MAX_PAYLOAD_SIZE:
        return JSONResponse(
            {"error": f"payload too large (max {MAX_PAYLOAD_SIZE} bytes)"},
            status_code=413,
        )

    task_name = body.get("task_name")
    queue_name = body.get("queue_name", "default")
    module_path = body.get("module_path", "")
    args = body.get("args", [])
    kwargs = body.get("kwargs", {})

    if not task_name:
        return JSONResponse({"error": "task_name is required"}, status_code=400)
    if not module_path:
        return JSONResponse({"error": "module_path is required"}, status_code=400)

    task_id = await storage.enqueue(
        task_name=task_name,
        queue_name=queue_name,
        module_path=module_path,
        args=args,
        kwargs=kwargs,
    )
    return JSONResponse({"task_id": str(task_id)}, status_code=201)


async def queue_stats(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage
    stats = await storage.queue_stats()
    return JSONResponse(stats)


async def list_tasks(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage
    queue_name = request.query_params.get("queue")
    status = request.query_params.get("status")
    limit = int(request.query_params.get("limit", "50"))
    tasks = await storage.list_tasks(queue_name=queue_name, status=status, limit=limit)
    return JSONResponse([_serialize_task(t) for t in tasks])


async def get_task(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage
    task_id = _parse_uuid(request.path_params["task_id"])
    if task_id is None:
        return JSONResponse({"error": "invalid task id"}, status_code=400)
    task = await storage.get_task(task_id)
    if task is None:
        return JSONResponse({"error": "task not found"}, status_code=404)
    return JSONResponse(_serialize_task(task))


async def cancel_task(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage
    task_id = _parse_uuid(request.path_params["task_id"])
    if task_id is None:
        return JSONResponse({"error": "invalid task id"}, status_code=400)
    cancelled = await storage.cancel_task(task_id)
    if not cancelled:
        return JSONResponse({"error": "task not found or not pending"}, status_code=404)
    return JSONResponse({"status": "cancelled"})


async def queues_html_endpoint(request: Request) -> HTMLResponse:
    storage: Storage = request.app.state.storage
    stats = await storage.queue_stats()
    return queues_html(stats)


async def tasks_html_endpoint(request: Request) -> HTMLResponse:
    storage: Storage = request.app.state.storage
    queue_name = request.query_params.get("queue")
    status = request.query_params.get("status")
    limit = int(request.query_params.get("limit", "20"))
    tasks = await storage.list_tasks(queue_name=queue_name, status=status, limit=limit)
    serialized = [_serialize_task(t) for t in tasks]
    return tasks_html(serialized)


async def dashboard(request: Request) -> HTMLResponse:
    return dashboard_page


async def health(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage
    try:
        async with storage.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return JSONResponse({"status": "ok", "database": "connected"})
    except Exception as e:
        return JSONResponse({"status": "error", "database": str(e)}, status_code=503)


def _serialize_task(task: dict[str, Any]) -> dict[str, Any]:
    result = dict(task)
    for key in ("id",):
        if key in result and isinstance(result[key], uuid.UUID):
            result[key] = str(result[key])
    for key in ("created_at", "started_at", "completed_at", "scheduled_at"):
        if key in result and result[key] is not None:
            result[key] = result[key].isoformat()
    return result


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


def _estimate_size(obj: Any) -> int:
    import json

    return len(json.dumps(obj, default=str))
