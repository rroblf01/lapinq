# Lagomorph

**A lightweight task queue with PostgreSQL backend — replacing Celery + RabbitMQ with a single container.**

## Features

- **Simple API**: Decorate your functions with `@tasks.task()` to enqueue them
- **PostgreSQL-backed**: No separate broker needed — tasks are stored in PostgreSQL
- **Rust executor**: Task functions execute via embedded Rust (PyO3) for sync tasks, avoiding subprocess overhead
- **Inline worker**: Run server + worker in a single process with `--worker` flag
- **Real-time dashboard**: WebSocket-powered dashboard with instant updates via PostgreSQL `LISTEN`/`NOTIFY`
- **TTL support**: Configure task expiration — tasks are automatically cleaned up after a configurable TTL
- **Rich filtering**: Search tasks by ID, status, queue, args, result, and error content
- **DLQ (Dead Letter Queue)**: Failed tasks are available for inspection and requeue
- **Prometheus metrics**: Expose task queue metrics for monitoring
- **Configurable concurrency**: Control how many tasks run simultaneously
- **Rust worker** (optional): High-performance standalone worker binary
- **Auth & Rate limiting**: Optional API key authentication and per-IP rate limiting
- **PyPI package**: Install with `pip install lagomorph`

## Quick Start

```python
from lagomorph import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001", queue_name="video")

@tasks.task(name="process_video")
def process_video(video_id: int, codec: str):
    print(f"Processing video {video_id} with {codec}")

# Enqueue the task — sends HTTP POST to the server
response = process_video.queue(1, codec="h264")
task_id = response.json()["task_id"]
```

## Architecture

```
┌──────────────┐     HTTP      ┌──────────────────┐     SQL      ┌────────────┐
│  Web App     │ ──────────►   │  Lagomorph Server│ ─────────►   │ PostgreSQL │
│  (FastAPI/   │               │  (Starlette +     │              │            │
│   Django)    │               │   Inline Worker)  │              │  tasks     │
│              │               │  - REST API       │              └────────────┘
└──────────────┘               │  - Dashboard (WS) │
                               │  - Worker (opt.)  │
                               └───────────────────┘
```

Or with separate Rust worker for production:

```
┌──────────────┐     HTTP      ┌──────────────────┐
│  Web App     │ ──────────►   │  Lagomorph Server│ ────┐
│  (FastAPI/   │               │  (no worker)      │     │
│   Django)    │               └───────────────────┘     │  SQL
│              │                                         │
└──────────────┘               ┌──────────────────┐     │
                               │  Rust Worker     │ ◄───┘
                               │  (lagomorph-     │
                               │   worker binary) │
                               └──────────────────┘
```
