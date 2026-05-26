# Server API Reference

## `create_app(database_url, api_key, session_secret, rate_limit, worker, ...)`

Create a Starlette ASGI app with the lapinq REST API, dashboard, and optional inline worker.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_url` | `str` | `"postgresql://localhost:5432/lapinq"` | PostgreSQL connection URL |
| `api_key` | `str \| None` | `None` | API key for API auth middleware |
| `session_secret` | `str \| None` | `None` | Secret for dashboard session cookies (auto-generated if empty) |
| `rate_limit` | `int` | `0` | Max requests/min per IP (`0` = disabled) |
| `worker` | `bool` | `False` | Run inline worker in-process |
| `worker_concurrency` | `int` | `4` | Inline worker concurrency |
| `worker_poll_interval` | `float` | `0.1` | Worker DB poll interval (seconds) |
| `worker_timeout` | `int` | `300` | Task timeout (seconds) |
| `cleanup_interval` | `float` | `0` | TTL cleanup interval (`0` = disabled) |
| `scheduler` | `bool` | `False` | Run cron-based periodic scheduler in-process |
| `scheduler_interval` | `int` | `60` | Scheduler tick interval (seconds) |

## Endpoints

### `POST /api/v1/enqueue`

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
    "ttl_seconds": 86400,
    "metadata": {"source": "web", "user_id": 42},
    "retry_delay": 30,
    "retry_backoff": false,
    "webhook_url": "https://myapp.com/webhooks/task-complete"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `task_name` | `str` | Name of the task function |
| `queue_name` | `str` | Queue to enqueue in |
| `module_path` | `str` | Python module to import |
| `args` | `list` | Positional arguments |
| `kwargs` | `object` | Keyword arguments |
| `scheduled_at` | `str` | ISO 8601 datetime for delayed execution |
| `max_retries` | `int` | Max retry attempts (default 3) |
| `priority` | `int` | Higher = runs first (default 0) |
| `ttl_seconds` | `int` | Auto-delete after N seconds; `0` = do not persist |
| `metadata` | `object` | Arbitrary JSONB key-value pairs |
| `retry_delay` | `int` | Fixed delay between retries (seconds) |
| `retry_backoff` | `bool` | Exponential backoff (default `true`) |
| `webhook_url` | `str` | URL called on task completion/failure |

**Response:** `201 Created`

```json
{"task_id": "uuid-here"}
```

If `ttl_seconds` is `0`, the task is not persisted:

```json
{"task_id": null, "ttl_seconds": 0}
```

### `POST /api/v1/enqueue/batch`

Enqueue multiple tasks in a single request (up to 1000).

**Request body:**

```json
[
    {"task_name": "add", "queue_name": "batch", "module_path": "myapp.tasks", "args": [1, 2], "max_retries": 0},
    {"task_name": "add", "queue_name": "batch", "module_path": "myapp.tasks", "args": [3, 4], "max_retries": 0}
]
```

**Response:** `201 Created`

```json
{"task_ids": ["uuid-1", "uuid-2"]}
```

### `PATCH /api/v1/tasks/{id}/progress`

Update progress for a running task.

**Request body:**

```json
{
    "progress": 50,
    "message": "Processing frame 50/100"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `progress` | `int` | Progress percentage (0–100) |
| `message` | `str` | Optional progress description |

**Response:** `200 OK`

### `GET /api/v1/tasks/{id}/result`

Get only the result of a completed task.

**Response:** `200 OK`

```json
{"id": "uuid", "status": "completed", "result": "\"done\"", "error": null, "completed_at": "2026-01-01T00:00:00"}
```

Returns `{"error": "task not finished"}` with current status if not yet completed.

### `GET /api/v1/queues`

Queue statistics — pending/running/completed/failed counts per queue.

**Response:** `200 OK`

### `GET /api/v1/tasks`

List tasks.

| Query param | Default | Description |
|-------------|---------|-------------|
| `queue` | — | Filter by queue name |
| `status` | — | Filter by status (`pending`, `running`, `completed`, `failed`, `cancelled`, `expired`) |
| `task_name` | — | Filter by task name (ILIKE) |
| `limit` | `50` | Max results |

### `DELETE /api/v1/tasks`

Bulk-delete tasks matching filters. Requires admin session or `X-API-Key`.

| Query param | Description |
|-------------|-------------|
| `queue` | Filter by queue name |
| `status` | Filter by status |
| `task_name` | Filter by task name (ILIKE) |
| `args` | Filter by args content (ILIKE) |
| `result` | Filter by result content (ILIKE) |
| `error` | Filter by error content (ILIKE) |

**Response:** `200 OK`

```json
{"deleted": 5}
```

### `GET /api/v1/tasks/failed`

List failed tasks (Dead Letter Queue).

| Query param | Default | Description |
|-------------|---------|-------------|
| `queue` | — | Filter by queue name |
| `limit` | `50` | Max results |

### `GET /api/v1/tasks/{id}`

Get a single task by ID.

**Response:** `200 OK` with full task details, or `404 Not Found`.

### `DELETE /api/v1/tasks/{id}`

Cancel a pending task (sets status to `cancelled`).

**Response:** `200 OK` or `404 Not Found`.

### `POST /api/v1/tasks/{id}/requeue`

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

### `GET /login` — Login Page

HTML login form. Shows "Invalid credentials" on failed login. Redirects to dashboard on success.

### `POST /login`

Form-based login. Accepts `username` and `password` form fields. Sets a session cookie on success.

### `GET /logout`

Clears the session cookie and redirects to `/login`.

### `GET /` — Dashboard

HTML dashboard with session-based auth, real-time updates via WebSocket at `/ws`. The first user is auto-created as `lapinq`/`lapinq` with admin role.

### `GET /admin/users` — User Management (admin only)

HTML page to create, edit roles, edit permissions, and delete users.

### `POST /admin/users`

Create a new user (admin only). Accepts JSON:

```json
{"username": "newuser", "password": "secret", "role": "user"}
```

### `POST /admin/users/{id}/role`

Change a user's role (admin only). Accepts JSON:

```json
{"role": "admin"}
```

### `POST /admin/users/{id}/permissions`

Set per-queue permissions (admin only). Accepts JSON:

```json
{"queues": {"video": ["delete", "cancel"]}}
```

### `DELETE /admin/users/{id}`

Delete a user (admin only).

### `POST /account/password`

Change own password. Accepts JSON:

```json
{"current_password": "old", "new_password": "new"}
```

### `GET /me`

Returns current user info (id, username, role, permissions).

### `WebSocket /ws`

Real-time dashboard data. **First message must be authentication:**

```json
{"type": "auth", "token": "<session-token>"}
```

After auth the server sends JSON with `cards` and `table` HTML fragments every 2 seconds or immediately when tasks change (via PostgreSQL `LISTEN`/`NOTIFY`). The response also includes a `user` object with `role` and `username`.

**Client → Server filter messages:**

```json
{"queue": "video"}
{"id": "3cd39f6d..."}
{"status": "failed"}
{"task_name": "process"}
{"args": "keyword"}
{"result": "success"}
{"error": "timeout"}
```

## Middleware

### DashboardAuthMiddleware

Applied automatically to all dashboard routes. Checks the `lapinq_session` cookie on every request. If invalid or missing for protected paths (`/`, `/ws`, `/admin/*`, `/account/*`), redirects to `/login`. The `/login`, `/health`, and `/metrics` paths are always public.

### AuthMiddleware

Set `LAPINQ_API_KEY` env var or pass `api_key` to `create_app()`. All `/api/*` routes require either `X-API-Key` header (except `OPTIONS`) or a valid session cookie from dashboard login. This allows dashboard JS to call API endpoints seamlessly.

### RateLimitMiddleware

Set `LAPINQ_RATE_LIMIT` env var or pass `rate_limit` to `create_app()`. Limits requests per IP per minute on `/api/*` routes.

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

Session secret is read from `LAPINQ_SESSION_SECRET` env var. If unset, a random secret is generated on every startup (which invalidates all existing sessions after restart). Set a fixed value in production:

```bash
LAPINQ_SESSION_SECRET=your-secret-key python -m lapinq server
```
