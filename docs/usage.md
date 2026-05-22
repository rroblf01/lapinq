# Usage Guide

## TaskQueue Client

The `TaskQueue` class is the main entry point for enqueuing tasks.

### Configuration

```python
from lagomorph import TaskQueue

tasks = TaskQueue(
    server_url="http://worker:8001",  # The lagomorph server URL
    queue_name="default",              # Default queue name
    timeout=30.0,                      # HTTP request timeout
)
```

### Defining Tasks

```python
@tasks.task(name="send_email")
def send_email(to: str, subject: str, body: str):
    # This code runs on the worker
    print(f"Sending email to {to}: {subject}")

@tasks.task(name="process_image", queue_name="images")
def process_image(image_id: int, quality: int = 80):
    # Override queue name per-task
    pass
```

### Enqueuing Tasks

When you call a decorated function, it sends an HTTP POST to the server:

```python
# These calls return immediately — the task runs on the worker
response = send_email(to="user@example.com", subject="Hello", body="World")
task_id = response.json()["task_id"]
```

### Multiple Queues

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

## REST API

The lagomorph server exposes a REST API for task management.

### Enqueue a task

```bash
curl -X POST http://localhost:8001/api/enqueue \
  -H "Content-Type: application/json" \
  -d '{"task_name": "my_task", "queue_name": "default", "module_path": "myapp.tasks", "args": [1], "kwargs": {"key": "value"}}'
```

### List tasks

```bash
curl http://localhost:8001/api/tasks?limit=10
```

### Get queue stats

```bash
curl http://localhost:8001/api/queues
```

### Cancel a task

```bash
curl -X DELETE http://localhost:8001/api/tasks/<task_id>
```

### Health check

```bash
curl http://localhost:8001/health
```

## Dashboard

Open `http://localhost:8001/dashboard` in your browser for the real-time HTMX dashboard.

![Dashboard preview](dashboard.png)

The dashboard auto-refreshes every 3 seconds and shows:
- Queue names with pending/running counts
- Recent tasks table with status badges
- Manual refresh button
