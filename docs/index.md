# Lagomorph

**A lightweight task queue with PostgreSQL backend — replacing Celery + RabbitMQ with a single container.**

## Features

- **Simple API**: Decorate your functions with `@tasks.task()` to enqueue them
- **PostgreSQL-backed**: No separate broker needed — tasks are stored in PostgreSQL
- **Dashboard**: Real-time HTMX dashboard to monitor queues and tasks
- **Configurable concurrency**: Control how many tasks run simultaneously
- **Rust worker** (optional): High-performance worker binary compiled from Rust
- **Python worker** (built-in): Native Python worker for development
- **PyPI package**: Install with `pip install lagomorph`

## Quick Start

```python
from lagomorph import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001", queue_name="video")

@tasks.task(name="procesar_video")
def procesar_video(video_id: int, codec: str):
    # Your task logic here
    print(f"Processing video {video_id} with {codec}")

# Enqueue the task — sends HTTP POST to the server
procesar_video(video_id=1, codec="h264")
```

## Architecture

```
┌──────────────┐     HTTP      ┌──────────────────┐     SQL      ┌────────────┐
│  Web App     │ ──────────►   │  Python Server   │ ─────────►   │ PostgreSQL │
│  (FastAPI/   │               │  (Starlette)      │              │            │
│   Django)    │               │  - REST API       │              │  tasks     │
│              │               │  - Dashboard      │              └────────────┘
└──────────────┘               └────────┬─────────┘
                                         │
                                ┌────────▼─────────┐
                                │  Worker           │
                                │  (Rust or Python) │
                                │  - Polls DB       │
                                │  - Executes tasks │
                                └───────────────────┘
```
