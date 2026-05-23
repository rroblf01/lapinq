# Examples

This page shows how to use Lapinq with **FastAPI** and **Django** — the two most common web frameworks for Python.

All source code is available in the `examples/` directory of the repository.

---

## FastAPI

### Installation

```bash
pip install lapinq fastapi uvicorn
```

### Define Tasks

Create a file `tasks.py`:

```python
from __future__ import annotations

import asyncio
import time

from lapinq.client import AsyncTaskQueue

task_queue = AsyncTaskQueue(
    server_url="http://localhost:8001",
    queue_name="default",
)


@task_queue.task(name="slow_square", max_retries=0)
def slow_square(n: int) -> int:
    time.sleep(2)         # Simulate CPU work
    return n * n


@task_queue.task(name="echo_message", max_retries=0)
async def echo_message(msg: str) -> str:
    await asyncio.sleep(0.1)  # Simulate I/O
    return f"echo: {msg}"
```

### Create the FastAPI App

```python
from fastapi import FastAPI, HTTPException
from tasks import slow_square, echo_message

app = FastAPI(title="Lapinq + FastAPI Demo")


@app.post("/square/{n}")
async def enqueue_square(n: int):
    """Enqueue a slow square calculation."""
    resp = await slow_square.aqueue(n)
    if resp.status_code != 201:
        raise HTTPException(status_code=resp.status_code, detail=resp.json())
    return resp.json()


@app.post("/echo")
async def enqueue_echo(msg: str = "hello"):
    """Enqueue an async echo task."""
    resp = await echo_message.aqueue(msg)
    if resp.status_code != 201:
        raise HTTPException(status_code=resp.status_code, detail=resp.json())
    return resp.json()


@app.get("/task/{task_id}")
async def get_task(task_id: str):
    """Check task status and result."""
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://localhost:8001/api/v1/tasks/{task_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()
```

### Run

**Terminal 1** — Lapinq server with built-in worker:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/lapinq \
python -m lapinq server --worker --port 8001
```

**Terminal 2** — FastAPI dev server:

```bash
uvicorn app:app --reload --port 8000
```

### Test the Flow

```bash
# Enqueue a slow square
curl -X POST http://localhost:8000/square/5
# → {"task_id": "abc-1234-..."}

# Check the result
curl http://localhost:8001/api/v1/tasks/abc-1234-.../result
# → {"id": "abc-1234-...", "status": "completed", "result": "25", ...}

# Enqueue an async echo
curl -X POST "http://localhost:8000/echo?msg=hello%20world"
# → {"task_id": "def-5678-..."}

# Check result
curl http://localhost:8001/api/v1/tasks/def-5678-.../result
# → {"id": "def-5678-...", "status": "completed", "result": "\"echo: hello world\"", ...}
```

### Expected Results

| Task | Input | Result |
|------|-------|--------|
| `slow_square(5)` | `5` | `25` |
| `echo_message("hello world")` | `"hello world"` | `"echo: hello world"` |

---

## Django

### Installation

```bash
pip install lapinq django
```

### Define Tasks

Create a file `tasks.py` in your Django app:

```python
from __future__ import annotations

from lapinq.client import TaskQueue

# Point to the Lapinq server
task_queue = TaskQueue(
    server_url="http://localhost:8001",
    queue_name="django",
)


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@task_queue.task(name="hello", max_retries=0)
def hello(name: str, greeting: str = "Hello") -> str:
    """Return a greeting message."""
    return f"{greeting}, {name}!"
```

### Create a Django View

In `views.py`:

```python
from django.http import JsonResponse
from .tasks import add, hello


def enqueue_add(request, a, b):
    """Enqueue an add task."""
    resp = add.queue(a, b)
    return JsonResponse(resp.json())


def enqueue_hello(request, name):
    """Enqueue a hello task."""
    resp = hello.queue(name, greeting="Hi")
    return JsonResponse(resp.json())


def task_status(request, task_id):
    """Check task status. Proxies to the Lapinq API."""
    import httpx

    resp = httpx.get(f"http://localhost:8001/api/v1/tasks/{task_id}")
    return JsonResponse(resp.json())
```

In `urls.py`:

```python
from django.urls import path
from . import views

urlpatterns = [
    path("add/<int:a>/<int:b>/", views.enqueue_add),
    path("hello/<str:name>/", views.enqueue_hello),
    path("task/<uuid:task_id>/", views.task_status),
]
```

### Run

**Terminal 1** — Lapinq server with worker:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/lapinq \
python -m lapinq server --worker --port 8001
```

**Terminal 2** — Django dev server:

```bash
python manage.py runserver 0.0.0.0:8000
```

### Test the Flow

```bash
# Enqueue add(10, 20)
curl http://localhost:8000/add/10/20/
# → {"task_id": "abc-1234-..."}

# Check the result (via Lapinq API)
curl http://localhost:8001/api/v1/tasks/abc-1234-.../result
# → {"id": "abc-1234-...", "status": "completed", "result": "30", ...}

# Enqueue hello
curl http://localhost:8000/hello/World/
# → {"task_id": "def-5678-..."}

# Check result
curl http://localhost:8001/api/v1/tasks/def-5678-.../result
# → {"id": "def-5678-...", "status": "completed", "result": "\"Hi, World!\"", ...}
```

### Expected Results

| Task | Input | Result |
|------|-------|--------|
| `add(10, 20)` | `10, 20` | `30` |
| `hello("World", greeting="Hi")` | `"World"` | `"Hi, World!"` |

---

## Using the Client Library Directly

You don't need FastAPI or Django to use Lapinq — the client library works from any Python script:

```python
from lapinq.client import TaskQueue

tq = TaskQueue(server_url="http://localhost:8001")


@tq.task(name="greet")
def greet(name: str) -> str:
    return f"Hello, {name}!"


# Enqueue a task. The function also works normally:
result = greet.queue("World")
task_id = result.json()["task_id"]
```

For async code:

```python
from lapinq.client import AsyncTaskQueue

tq = AsyncTaskQueue(server_url="http://localhost:8001")


@tq.task(name="greet_async")
async def greet_async(name: str) -> str:
    return f"Hello, {name}!"


# In an async context:
result = await greet_async.aqueue("World")
```

---

## Common Patterns

### Running an Inline Worker (Simplest Setup)

Combine server and worker in one process:

```bash
python -m lapinq server --worker --port 8001
```

### Separate Server and Worker (Production)

Run the server without a worker:

```bash
python -m lapinq server --port 8001
```

Run one or more Python workers:

```bash
python -m lapinq worker --concurrency 4
```

Or the Rust worker (requires compilation):

```bash
lapinq-worker --database-url $DATABASE_URL --concurrency 4
```

### Checking Task Results

Use the dedicated result endpoint:

```bash
curl http://localhost:8001/api/v1/tasks/<task_id>/result
```

Returns immediately if the task is finished, or returns `"error": "task not finished"` with the current status.
