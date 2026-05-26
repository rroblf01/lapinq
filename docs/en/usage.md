# Usage Guide

## TaskQueue Client

The `TaskQueue` class is the main entry point for defining and enqueuing tasks synchronously.

### Configuration

```python
from lapinq import TaskQueue

tasks = TaskQueue(
    server_url="http://worker:8001",
    queue_name="default",
    timeout=30.0,
    api_key=None,
    default_ttl_seconds=None,
)
```

### AsyncTaskQueue

```python
from lapinq import AsyncTaskQueue

tasks = AsyncTaskQueue(
    server_url="http://worker:8001",
    queue_name="default",
    api_key=None,
    default_ttl_seconds=None,
)
```

### Defining Tasks

Tasks can be decorated with or without parentheses:

```python
@tasks.task  # no parens — uses function name
def send_email(to: str, subject: str, body: str):
    print(f"Sending email to {to}: {subject}")

@tasks.task(name="process_image", queue_name="images", priority=10)
def process_image(image_id: int, quality: int = 80):
    pass

@tasks.task(name="long_task", ttl_seconds=3600)
def long_task(data: str):
    """Task auto-deletes 1 hour after creation."""
    pass
```

The decorated function remains callable as the original:

```python
send_email(to="user@example.com", subject="Hello", body="World")  # calls directly
```

### Enqueuing Tasks

Enqueuing sends an HTTP POST to the server and returns a `TaskRef`:

```python
# Sync client — returns TaskRef
ref = send_email.queue(to="user@example.com", subject="Hello", body="World")
print(ref.task_id)           # "uuid-here"
print(ref.wait(timeout=30))  # poll until completed

# Async client — returns TaskRef
ref = await send_email.aqueue(to="user@example.com", subject="Hello", body="World")
result = await ref.awaitait(timeout=30)
print(result["status"])
```

### Task Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `scheduled_at` | `str` (ISO 8601) | Delay execution until this time |
| `max_retries` | `int` | Max retry attempts on failure (default 3) |
| `priority` | `int` | Higher values execute first (default 0) |
| `ttl_seconds` | `int` | Auto-delete task after N seconds; `0` = don't persist |
| `metadata` | `dict` | Arbitrary key-value pairs stored as JSONB |
| `retry_delay` | `float` | Fixed delay between retries (seconds) |
| `retry_backoff` | `bool` | Exponential backoff (default `true`) |
| `webhook_url` | `str` | URL called via POST on completion/failure |

```python
@tasks.task(name="delayed", scheduled_at="2026-06-15T12:30:00Z")
def delayed_task():
    pass

@tasks.task(name="no_retry", max_retries=0)
def fragile_task():
    pass

@tasks.task(name="volatile", ttl_seconds=0)
def noop():
    pass  # This task is discarded immediately

@tasks.task(name="with_meta", metadata={"source": "web"}, webhook_url="https://myapp.com/webhook")
def webhook_task():
    pass
```

## REST API

### Enqueue a task

```bash
curl -X POST http://localhost:8001/api/v1/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "my_task",
    "queue_name": "default",
    "module_path": "myapp.tasks",
    "args": [1],
    "kwargs": {"key": "value"},
    "priority": 5,
    "max_retries": 3,
    "ttl_seconds": 86400,
    "scheduled_at": "2026-06-15T12:00:00Z"
  }'
```

### List tasks

```bash
curl "http://localhost:8001/api/v1/tasks?limit=10&status=pending&queue=default&task_name=process"
```

### Get task stats

```bash
curl http://localhost:8001/api/v1/queues
```

### Get a single task

```bash
curl http://localhost:8001/api/v1/tasks/<task_id>
```

### Cancel a pending task

```bash
curl -X DELETE http://localhost:8001/api/v1/tasks/<task_id>
```

### Requeue a failed task

```bash
curl -X POST http://localhost:8001/api/v1/tasks/<task_id>/requeue
```

### Bulk-delete tasks by filter

```bash
curl -X DELETE "http://localhost:8001/api/v1/tasks?status=failed&queue=default"
```

Supports all filter params: `queue`, `status`, `task_name`, `args`, `result`, `error`.

### List failed tasks (DLQ)

```bash
curl http://localhost:8001/api/v1/tasks/failed
```

### Health check

```bash
curl http://localhost:8001/health
```

### Prometheus metrics

```bash
curl http://localhost:8001/metrics
```

## CLI Task Management

```bash
# List tasks
lapinq task list --status pending --limit 20 --json

# Get a single task
lapinq task get <task_id> --json

# Cancel a pending task
lapinq task cancel <task_id>

# Requeue a failed task
lapinq task requeue <task_id>
```

## Cron-based Scheduler

Schedule recurring tasks using 5-field cron expressions:

```bash
lapinq server --scheduler --scheduler-interval 60
```

Define schedules by inserting rows into the `lapinq_scheduled_tasks` table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID` | Primary key |
| `task_name` | `TEXT` | Name of the task function |
| `module_path` | `TEXT` | Python module to import |
| `queue_name` | `TEXT` | Queue to enqueue in |
| `cron_expression` | `TEXT` | 5-field cron (`min hour day month weekday`) |
| `args` | `JSONB` | Positional arguments |
| `kwargs` | `JSONB` | Keyword arguments |
| `enabled` | `BOOLEAN` | `true` = active, `false` = skipped |

Example — execute `my_task.every_minute` every minute:

```sql
INSERT INTO lapinq_scheduled_tasks
    (task_name, module_path, queue_name, cron_expression, args, kwargs, enabled)
VALUES
    ('every_minute', 'myapp.tasks', 'default', '* * * * *', '[]', '{}', true);
```

## Dashboard

Open [http://localhost:8001](http://localhost:8001) in your browser. Login with the default admin account (`lapinq`/`lapinq`).

Features:
- **Session-based auth**: Dashboard requires login. Logout button in the header.
- **Real-time updates**: WebSocket connection pushes changes instantly (backed by PostgreSQL `LISTEN`/`NOTIFY`)
- **Queue cards**: Active/pending/completed/failed counts per queue
- **Task table**: ID, task name, queue, args, result, error, status, and TTL remaining
- **Filters**: Queue, status, task name, task ID, args content, result content, error content
- **Cancel/Requeue**: Admins can cancel pending tasks or requeue failed tasks inline
- **Delete filtered**: Admins can bulk-delete tasks matching current filters
- **Change password**: Any authenticated user can change their own password
- **User management** (admin only): Create users, change roles, set per-queue permissions
- **TTL display**: Shows remaining time before auto-deletion or `∞` for permanent tasks

## TTL Cleanup

Enable automatic cleanup of expired tasks:

```bash
python -m lapinq server --worker --cleanup-interval 300
```

This deletes tasks where `created_at + ttl_seconds < now()` every 5 minutes.

## Multiple Queues

```python
video_tasks = TaskQueue(server_url="http://worker:8001", queue_name="video")
audio_tasks = TaskQueue(server_url="http://worker:8001", queue_name="audio")

@video_tasks.task(name="transcode")
def transcode_video(video_id: int):
    pass

@audio_tasks.task(name="convert")
def convert_audio(audio_id: int):
    pass
```
