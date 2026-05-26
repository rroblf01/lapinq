# Getting Started

## Installation

### From PyPI

```bash
pip install lapinq
```

### From source

```bash
git clone https://github.com/ricardorobles/lapinq.git
cd lapinq
pip install maturin
maturin develop
```

## Starting PostgreSQL

```bash
docker run -d --name lapinq-db \
  -e POSTGRES_USER=lapinq \
  -e POSTGRES_PASSWORD=lapinq \
  -e POSTGRES_DB=lapinq \
  -p 5432:5432 \
  postgres:16-alpine
```

## Start Server + Inline Worker (simplest)

Run both the HTTP server and task worker in a single process:

```bash
python -m lapinq server --worker --port 8001
```

This is the easiest way to get started. The inline worker executes tasks in-process using the Rust executor (PyO3) for sync functions.

## Start Server with Separate Worker

### Terminal 1 — Server:

```bash
python -m lapinq server --port 8001
```

### Terminal 2 — Python worker:

```bash
python -m lapinq worker --concurrency 4
```

### Terminal 2 — Rust worker (production):

```bash
lapinq-worker --database-url postgresql://lapinq:lapinq@localhost:5432/lapinq --concurrency 4
```

## Dashboard

Open [http://localhost:8001](http://localhost:8001) in your browser. The dashboard shows queue statistics and recent tasks with real-time updates via WebSocket.

## Your First Task

```python
from lapinq import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001")

@tasks.task(name="hello")
def hello(name: str):
    return f"Hello, {name}!"

# Enqueue — returns a TaskRef
ref = hello.queue(name="World")
print(ref.task_id)  # "uuid-..."
print(ref.wait(timeout=30))  # poll for result
```

## Task TTL (Time To Live)

Tasks expire automatically after a configurable time. Set `ttl_seconds` when enqueuing.

### Keep for 1 day (86400s)

```python
ref = hello.queue(name="World", ttl_seconds=86400)
```

### Keep for 1 minute (60s)

```python
ref = hello.queue(name="World", ttl_seconds=60)
```

### Don't persist (0 = no TTL, task remains until completed or archived)

```python
ref = hello.queue(name="World", ttl_seconds=0)
```

> `ttl_seconds=0` disables expiry for that task. The server never deletes it unless you archive old tasks with `--archive-after-days` (default 30) or delete manually via the dashboard.

### Enable periodic cleanup

The server must run with `--cleanup-interval` to expire tasks automatically:

```bash
python -m lapinq server --worker --port 8001 --cleanup-interval 60
```

This checks for expired tasks every 60 seconds. Without this flag, TTL is stored but never enforced.

## Async Client

```python
from lapinq import AsyncTaskQueue

async def main():
    tasks = AsyncTaskQueue(server_url="http://localhost:8001")

    @tasks.task(name="hello")
    async def hello(name: str):
        return f"Hello, {name}!"

    ref = await hello.aqueue(name="World")
    result = await ref.awaitait(timeout=30)
    print(result["status"])

    await tasks.close()
```
