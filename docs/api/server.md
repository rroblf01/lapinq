# Server API Reference

## `create_app(database_url)`

Create a Starlette ASGI app with the lagomorph REST API.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_url` | `str` | `"postgresql://localhost:5432/lagomorph"` | PostgreSQL connection URL |

Returns a `starlette.applications.Starlette` instance.

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
    "kwargs": {"key": "value"}
}
```

**Response:** `201 Created`

```json
{"task_id": "uuid-here"}
```

### `GET /api/queues`

Get queue statistics (pending/running counts per queue).

### `GET /api/tasks`

List tasks. Supports query parameters: `queue`, `status`, `limit` (default 50).

### `GET /api/tasks/{id}`

Get a single task by ID.

### `DELETE /api/tasks/{id}`

Cancel a pending task by ID.

### `GET /health`

Health check endpoint. Returns `{"status": "ok"}`.

### `GET /dashboard`

HTML dashboard with HTMX real-time updates.
