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

# Enqueue — runs asynchronously on the worker
response = hello.queue(name="World")
print(response.json())  # {"task_id": "..."}
```

## Async Client

```python
from lapinq import AsyncTaskQueue

async def main():
    tasks = AsyncTaskQueue(server_url="http://localhost:8001")

    @tasks.task(name="hello")
    async def hello(name: str):
        return f"Hello, {name}!"

    response = await hello.aqueue(name="World")
    print(response.json())

    await tasks.close()
```
