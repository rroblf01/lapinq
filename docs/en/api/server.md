# Server API Reference

## `create_app(database_url, api_key, rate_limit, worker, ...)`

Create a Starlette ASGI app with the lapinq REST API, dashboard, and optional inline worker.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_url` | `str` | `"postgresql://localhost:5432/lapinq"` | PostgreSQL connection URL |
| `api_key` | `str \| None` | `None` | API key for auth middleware |
| `rate_limit` | `int` | `0` | Max requests/min per IP (`0` = disabled) |
| `worker` | `bool` | `False` | Run inline worker in-process |
| `worker_concurrency` | `int` | `4` | Inline worker concurrency |
| `worker_poll_interval` | `float` | `0.1` | Worker DB poll interval (seconds) |
| `worker_timeout` | `int` | `300` | Task timeout (seconds) |
| `cleanup_interval` | `float` | `0` | TTL cleanup interval (`0` = disabled) |

## Endpoints

### `POST /api/enqueue`

Enqueue a new task.

**Request body:**

```json
{
    "task_name": "my_task",
    "queue_name": "default",
    "module_path": "myapp.tasks",
    "args": [1, 2, 3],
    "kwargs": {"key": "value"},
    "scheduled_at": "2026-06-15T12:00:00Z",
    "max_retries": 3,
    "priority": 5,
    "ttl_seconds": 86400
}
```

**Response:** `201 Created`

```json
{"task_id": "uuid-here"}
```

If `ttl_seconds` is `0`, the task is not persisted:

```json
{"task_id": null, "ttl_seconds": 0}
```

### `GET /api/queues`

Queue statistics — pending/running/completed/failed counts per queue.

**Response:** `200 OK`

### `GET /api/tasks`

List tasks.

| Query param | Default | Description |
|-------------|---------|-------------|
| `queue` | — | Filter by queue name |
| `status` | — | Filter by status (`pending`, `running`, `completed`, `failed`) |
| `limit` | `50` | Max results |

### `GET /api/tasks/failed`

List failed tasks (Dead Letter Queue).

| Query param | Default | Description |
|-------------|---------|-------------|
| `queue` | — | Filter by queue name |
| `limit` | `50` | Max results |

### `GET /api/tasks/{id}`

Get a single task by ID.

**Response:** `200 OK` with full task details, or `404 Not Found`.

### `DELETE /api/tasks/{id}`

Cancel a pending task (deletes it).

**Response:** `200 OK` or `404 Not Found`.

### `POST /api/tasks/{id}/requeue`

Requeue a failed task back to `pending` status.

**Response:** `200 OK` or `404 Not Found` (if task is not failed).

### `GET /health`

Health check. Returns `{"status": "ok", "database": "connected"}`.

### `GET /metrics`

Prometheus-formatted metrics:

```
# HELP lapinq_tasks Task counts by queue and status
# TYPE lapinq_tasks gauge
lapinq_tasks{queue="default",status="pending"} 5
lapinq_tasks{queue="default",status="running"} 2
lapinq_tasks{queue="default",status="completed"} 100
lapinq_tasks{queue="default",status="failed"} 1
```

### `GET /` — Dashboard

HTML dashboard with WebSocket real-time updates at `/ws`.

### `WebSocket /ws`

Real-time dashboard data. Server sends JSON with `cards` and `table` HTML fragments every 2 seconds or immediately when tasks change (via PostgreSQL `LISTEN`/`NOTIFY`).

**Client → Server filter messages:**

```json
{"queue": "video"}
{"id": "3cd39f6d..."}
{"status": "failed"}
{"args": "keyword"}
{"result": "success"}
{"error": "timeout"}
```

## Middleware

### AuthMiddleware

Set `LAGOMORPH_API_KEY` env var or pass `api_key` to `create_app()`. All `/api/*` routes require `X-API-Key` header (except `OPTIONS`). Dashboard and health endpoints are public.

### RateLimitMiddleware

Set `LAGOMORPH_RATE_LIMIT` env var or pass `rate_limit` to `create_app()`. Limits requests per IP per minute on `/api/*` routes.

## CLI

```bash
python -m lapinq server \
  --host 0.0.0.0 \
  --port 8001 \
  --database-url postgresql://user:pass@localhost:5432/db \
  --worker \
  --worker-concurrency 4 \
  --cleanup-interval 300
```
