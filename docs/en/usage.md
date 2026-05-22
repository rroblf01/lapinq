# Usage Guide

## TaskQueue Client

The `TaskQueue` class is the main entry point for defining and enqueuing tasks synchronously.

### Configuration

```python
from lagomorph import TaskQueue

tasks = TaskQueue(
    server_url="http://worker:8001",
    queue_name="default",
    timeout=30.0,
)
```

### AsyncTaskQueue

```python
from lagomorph import AsyncTaskQueue

tasks = AsyncTaskQueue(
    server_url="http://worker:8001",
    queue_name="default",
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

Enqueuing sends an HTTP POST to the server and returns immediately:

```python
# Sync client
response = send_email.queue(to="user@example.com", subject="Hello", body="World")
task_id = response.json()["task_id"]

# Async client
response = await send_email.aqueue(to="user@example.com", subject="Hello", body="World")
task_id = response.json()["task_id"]
```

### Task Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `scheduled_at` | `str` (ISO 8601) | Delay execution until this time |
| `max_retries` | `int` | Max retry attempts on failure (default 3) |
| `priority` | `int` | Higher values execute first (default 0) |
| `ttl_seconds` | `int` | Auto-delete task after N seconds; `0` = don't persist |

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
```

## REST API

### Enqueue a task

```bash
curl -X POST http://localhost:8001/api/enqueue \
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
curl "http://localhost:8001/api/tasks?limit=10&status=pending&queue=default"
```

### Get task stats

```bash
curl http://localhost:8001/api/queues
```

### Get a single task

```bash
curl http://localhost:8001/api/tasks/<task_id>
```

### Cancel a pending task

```bash
curl -X DELETE http://localhost:8001/api/tasks/<task_id>
```

### Requeue a failed task

```bash
curl -X POST http://localhost:8001/api/tasks/<task_id>/requeue
```

### List failed tasks (DLQ)

```bash
curl http://localhost:8001/api/tasks/failed
```

### Health check

```bash
curl http://localhost:8001/health
```

### Prometheus metrics

```bash
curl http://localhost:8001/metrics
```

## Dashboard

Open [http://localhost:8001](http://localhost:8001) in your browser.

Features:
- **Real-time updates**: WebSocket connection pushes changes instantly (backed by PostgreSQL `LISTEN`/`NOTIFY`)
- **Queue cards**: Active/pending/completed/failed counts per queue
- **Task table**: ID, task name, queue, args, result, error, status, and TTL remaining
- **Filters**: Queue, status, task ID, args content, result content, error content
- **TTL display**: Shows remaining time before auto-deletion or `∞` for permanent tasks

## TTL Cleanup

Enable automatic cleanup of expired tasks:

```bash
python -m lagomorph server --worker --cleanup-interval 300
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
