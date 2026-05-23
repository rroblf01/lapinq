from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from lapinq.dashboard import _queue_cards_html, _tasks_table_html, dashboard_page, queues_html, tasks_html
from lapinq.storage import Storage
from lapinq.worker import run_worker_inline

logger = logging.getLogger("lapinq.server")

MAX_PAYLOAD_SIZE = int(os.environ.get("LAPINQ_MAX_PAYLOAD_SIZE", str(1024 * 100)))


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, api_key: str) -> None:
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            key = request.headers.get("X-API-Key")
            if key != self.api_key:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, max_requests: int, window_seconds: int = 60, max_clients: int = 10000) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._requests: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window_seconds
        self._evict(window_start)
        timestamps = self._requests.get(ip, [])
        timestamps = [t for t in timestamps if t > window_start]
        if len(timestamps) >= self.max_requests:
            return JSONResponse({"error": "rate limit exceeded"}, status_code=429)
        timestamps.append(now)
        self._requests[ip] = timestamps
        return await call_next(request)

    def _evict(self, window_start: float) -> None:
        stale = [ip for ip, ts in self._requests.items() if not any(t > window_start for t in ts)]
        for ip in stale:
            del self._requests[ip]
        if len(self._requests) > self.max_clients:
            sorted_ips = sorted(self._requests.items(), key=lambda x: max(x[1]), reverse=True)
            self._requests = dict(sorted_ips[:self.max_clients])


async def _cleanup_loop(storage: Storage, interval: float) -> None:
    while True:
        try:
            await asyncio.sleep(interval)
            await storage.cleanup_expired_tasks()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Cleanup loop error")


def create_app(
    database_url: str = "postgresql://localhost:5432/lapinq",
    api_key: str | None = None,
    rate_limit: int = 0,
    worker: bool = False,
    worker_concurrency: int = 4,
    worker_poll_interval: float = 0.1,
    worker_timeout: int = 300,
    cleanup_interval: float = 0,
) -> Starlette:
    routes = [
        Route("/", dashboard, methods=["GET"]),
        WebSocketRoute("/ws", ws_endpoint),
        Route("/api/enqueue", enqueue, methods=["POST"]),
        Route("/api/queues", queue_stats, methods=["GET"]),
        Route("/api/tasks/html", tasks_html_endpoint, methods=["GET"]),
        Route("/api/queues/html", queues_html_endpoint, methods=["GET"]),
        Route("/api/tasks", list_tasks, methods=["GET"]),
        Route("/api/tasks/failed", list_failed_tasks, methods=["GET"]),
        Route("/api/tasks/{task_id:str}", get_task, methods=["GET"]),
        Route("/api/tasks/{task_id:str}", cancel_task, methods=["DELETE"]),
        Route("/api/tasks/{task_id:str}/requeue", requeue_task, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/metrics", metrics, methods=["GET"]),
    ]

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None]:
        storage = await Storage.create(database_url)
        app.state.storage = storage
        app.state.cleanup_interval = cleanup_interval
        app.state.notification_event = asyncio.Event()
        await storage.listen_for_changes(app.state.notification_event.set)
        bg_tasks: list[asyncio.Task[None]] = []
        if worker:
            bg_tasks.append(
                asyncio.create_task(
                    run_worker_inline(
                        storage,
                        concurrency=worker_concurrency,
                        poll_interval=worker_poll_interval,
                        task_timeout=worker_timeout,
                    )
                )
            )
        if cleanup_interval > 0:
            bg_tasks.append(
                asyncio.create_task(_cleanup_loop(storage, cleanup_interval))
            )
        yield
        for t in bg_tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        await storage.close()

    cors_origins = os.environ.get("LAPINQ_CORS_ORIGINS", "*").split(",")
    middleware: list[Middleware] = [
        Middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ]
    if api_key is not None:
        middleware.append(Middleware(AuthMiddleware, api_key=api_key))
    if rate_limit > 0:
        middleware.append(Middleware(RateLimitMiddleware, max_requests=rate_limit))

    app = Starlette(routes=routes, lifespan=lifespan, middleware=middleware)
    return app


async def enqueue(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
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
    scheduled_at = body.get("scheduled_at")
    max_retries = body.get("max_retries", 3)
    priority = body.get("priority", 0)
    ttl_seconds = body.get("ttl_seconds")
    if ttl_seconds is not None:
        try:
            ttl_seconds = float(ttl_seconds)
        except (ValueError, TypeError):
            return JSONResponse({"error": "invalid ttl_seconds"}, status_code=400)

    if not task_name:
        return JSONResponse({"error": "task_name is required"}, status_code=400)
    if not module_path:
        return JSONResponse({"error": "module_path is required"}, status_code=400)

    if scheduled_at is not None:
        try:
            scheduled_at = datetime.fromisoformat(scheduled_at)
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return JSONResponse({"error": "invalid scheduled_at format"}, status_code=400)

    task_id = await storage.enqueue(
        task_name=task_name,
        queue_name=queue_name,
        module_path=module_path,
        args=args,
        kwargs=kwargs,
        scheduled_at=scheduled_at,
        max_retries=max_retries,
        priority=priority,
        ttl_seconds=ttl_seconds,
    )
    if task_id is None:
        return JSONResponse({"task_id": None, "ttl_seconds": 0}, status_code=201)
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


async def list_failed_tasks(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage
    queue_name = request.query_params.get("queue")
    limit = int(request.query_params.get("limit", "50"))
    tasks = await storage.list_failed_tasks(queue_name=queue_name, limit=limit)
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


async def requeue_task(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage
    task_id = _parse_uuid(request.path_params["task_id"])
    if task_id is None:
        return JSONResponse({"error": "invalid task id"}, status_code=400)
    requeued = await storage.requeue_task(task_id)
    if not requeued:
        return JSONResponse({"error": "task not found or not failed"}, status_code=404)
    return JSONResponse({"status": "requeued"})


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
    storage: Storage = request.app.state.storage
    stats = await storage.queue_stats()
    return dashboard_page(stats)


async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    storage: Storage = websocket.app.state.storage
    queue_filter: str | None = None
    id_filter: str | None = None
    status_filter: str | None = None
    args_search: str | None = None
    result_search: str | None = None
    error_search: str | None = None
    last_cards: str | None = None
    last_table: str | None = None
    changed = True
    notif_event: asyncio.Event | None = getattr(websocket.app.state, "notification_event", None)

    async def _send() -> None:
        nonlocal last_cards, last_table, changed
        try:
            if id_filter:
                raw = id_filter.strip()
                try:
                    tid = uuid.UUID(raw)
                    task = await storage.get_task(tid)
                    tasks = [_serialize_task(task)] if task else []
                except (ValueError, AttributeError):
                    tasks = await storage.list_tasks(limit=20)
                    tasks = [t for t in tasks if raw in str(t.get("id", ""))]
                stats = await storage.queue_stats()
            else:
                stats = await storage.queue_stats()
                tasks = await storage.list_tasks(
                    queue_name=queue_filter,
                    status=status_filter,
                    limit=200,
                )
                if args_search:
                    q = args_search.lower()
                    tasks = [t for t in tasks if q in str(t.get("args", "")).lower()]
                if result_search:
                    q = result_search.lower()
                    tasks = [t for t in tasks if q in str(t.get("result", "")).lower()]
                if error_search:
                    q = error_search.lower()
                    tasks = [t for t in tasks if q in str(t.get("error", "")).lower()]
                tasks = tasks[:20]
                if queue_filter:
                    stats = [s for s in stats if s["queue_name"] == queue_filter]
            cards = _queue_cards_html(stats)
            table = _tasks_table_html([_serialize_task(t) for t in tasks])
            if cards != last_cards or table != last_table or changed:
                last_cards, last_table, changed = cards, table, False
                payload: dict[str, Any] = {"cards": cards, "table": table}
                ci = getattr(websocket.app.state, "cleanup_interval", 0)
                if ci:
                    payload["cleanup_interval"] = ci
                await websocket.send_json(payload)
        except Exception:
            logger.exception("Error in WebSocket _send")

    await _send()

    try:
        while True:
            recv_task = asyncio.create_task(websocket.receive_json())
            if notif_event:
                notif_event.clear()
                notif_task = asyncio.create_task(notif_event.wait())
            else:
                notif_task = None
            pending: list[asyncio.Task[Any]] = [recv_task]
            if notif_task:
                pending.append(notif_task)

            done, _ = await asyncio.wait(pending, timeout=2, return_when=asyncio.FIRST_COMPLETED)

            if recv_task in done:
                data = recv_task.result()
                if "queue" in data:
                    queue_filter = data["queue"] or None
                    changed = True
                if "id" in data:
                    id_filter = data["id"] or None
                    changed = True
                if "status" in data:
                    status_filter = data["status"] or None
                    changed = True
                if "args" in data:
                    args_search = data["args"] or None
                    changed = True
                if "result" in data:
                    result_search = data["result"] or None
                    changed = True
                if "error" in data:
                    error_search = data["error"] or None
                    changed = True
            else:
                recv_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await recv_task

            if notif_task and notif_task not in done:
                notif_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await notif_task

            await _send()
    except WebSocketDisconnect:
        pass


async def health(request: Request) -> JSONResponse:
    storage: Storage = request.app.state.storage
    try:
        async with storage.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return JSONResponse({"status": "ok", "database": "connected"})
    except Exception as e:
        return JSONResponse({"status": "error", "database": str(e)}, status_code=503)


async def metrics(request: Request) -> Response:
    storage: Storage = request.app.state.storage
    stats = await storage.queue_stats()
    lines: list[str] = [
        "# HELP lapinq_tasks Task counts by queue and status",
        "# TYPE lapinq_tasks gauge",
    ]
    for q in stats:
        for status in ("pending", "running", "completed", "failed"):
            lines.append(
                f'lapinq_tasks{{queue="{q["queue_name"]}",status="{status}"}} {q[status]}'
            )
    lines.append("")
    return Response("\n".join(lines), media_type="text/plain; version=0.0.4")


def _format_ttl(created_at: datetime | None, ttl_seconds: float | None) -> str:
    if ttl_seconds is None:
        return "∞"
    if created_at is None:
        return f"{ttl_seconds}s"
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    deadline = created_at + timedelta(seconds=ttl_seconds)
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        return "expired"
    if remaining >= 86400:
        return f"{int(remaining // 86400)}d {int((remaining % 86400) // 3600)}h"
    if remaining >= 3600:
        return f"{int(remaining // 3600)}h {int((remaining % 3600) // 60)}m"
    if remaining >= 60:
        return f"{int(remaining // 60)}m {int(remaining % 60)}s"
    return f"{int(remaining)}s"


def _serialize_task(task: dict[str, Any]) -> dict[str, Any]:
    result = dict(task)
    for key in ("id",):
        if key in result and isinstance(result[key], uuid.UUID):
            result[key] = str(result[key])
    for key in ("created_at", "started_at", "completed_at", "scheduled_at", "last_heartbeat"):
        if key in result and result[key] is not None:
            result[key] = result[key].isoformat()
    result["ttl_remaining"] = _format_ttl(
        task.get("created_at"), task.get("ttl_seconds"),
    )
    return result


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


def _estimate_size(obj: Any) -> int:
    import json

    return len(json.dumps(obj, default=str))
