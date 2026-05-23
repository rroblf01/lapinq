# Ejemplos

Esta página muestra cómo usar Lapinq con **FastAPI** y **Django** — los dos frameworks web más comunes para Python.

Todo el código fuente está disponible en el directorio `examples/` del repositorio.

---

## FastAPI

### Instalación

```bash
pip install lapinq fastapi uvicorn
```

### Definir Tareas

Crea un archivo `tasks.py`:

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
    time.sleep(2)         # Simula trabajo de CPU
    return n * n


@task_queue.task(name="echo_message", max_retries=0)
async def echo_message(msg: str) -> str:
    await asyncio.sleep(0.1)  # Simula I/O
    return f"echo: {msg}"
```

### Crear la App FastAPI

```python
from fastapi import FastAPI, HTTPException
from tasks import slow_square, echo_message

app = FastAPI(title="Lapinq + FastAPI Demo")


@app.post("/square/{n}")
async def enqueue_square(n: int):
    """Encola un cálculo de cuadrado lento."""
    resp = await slow_square.aqueue(n)
    if resp.status_code != 201:
        raise HTTPException(status_code=resp.status_code, detail=resp.json())
    return resp.json()


@app.post("/echo")
async def enqueue_echo(msg: str = "hello"):
    """Encola una tarea async de eco."""
    resp = await echo_message.aqueue(msg)
    if resp.status_code != 201:
        raise HTTPException(status_code=resp.status_code, detail=resp.json())
    return resp.json()


@app.get("/task/{task_id}")
async def get_task(task_id: str):
    """Consulta el estado y resultado de una tarea."""
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://localhost:8001/api/v1/tasks/{task_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()
```

### Ejecutar

**Terminal 1** — Servidor Lapinq con worker incorporado:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/lapinq \
python -m lapinq server --worker --port 8001
```

**Terminal 2** — Servidor de desarrollo FastAPI:

```bash
uvicorn app:app --reload --port 8000
```

### Probar el Flujo

```bash
# Encolar un cuadrado lento
curl -X POST http://localhost:8000/square/5
# → {"task_id": "abc-1234-..."}

# Consultar el resultado
curl http://localhost:8001/api/v1/tasks/abc-1234-.../result
# → {"id": "abc-1234-...", "status": "completed", "result": "25", ...}

# Encolar un echo asíncrono
curl -X POST "http://localhost:8000/echo?msg=hola%20mundo"
# → {"task_id": "def-5678-..."}

# Consultar resultado
curl http://localhost:8001/api/v1/tasks/def-5678-.../result
# → {"id": "def-5678-...", "status": "completed", "result": "\"echo: hola mundo\"", ...}
```

### Resultados Esperados

| Tarea | Entrada | Resultado |
|-------|---------|-----------|
| `slow_square(5)` | `5` | `25` |
| `echo_message("hola mundo")` | `"hola mundo"` | `"echo: hola mundo"` |

---

## Django

### Instalación

```bash
pip install lapinq django
```

### Definir Tareas

Crea un archivo `tasks.py` en tu app Django:

```python
from __future__ import annotations

from lapinq.client import TaskQueue

task_queue = TaskQueue(
    server_url="http://localhost:8001",
    queue_name="django",
)


@task_queue.task(name="add", max_retries=0)
def add(a: int, b: int) -> int:
    """Suma dos números."""
    return a + b


@task_queue.task(name="hello", max_retries=0)
def hello(name: str, greeting: str = "Hello") -> str:
    """Devuelve un saludo."""
    return f"{greeting}, {name}!"
```

### Crear una Vista Django

En `views.py`:

```python
from django.http import JsonResponse
from .tasks import add, hello


def enqueue_add(request, a, b):
    """Encola una tarea de suma."""
    resp = add.queue(a, b)
    return JsonResponse(resp.json())


def enqueue_hello(request, name):
    """Encola una tarea de saludo."""
    resp = hello.queue(name, greeting="Hola")
    return JsonResponse(resp.json())


def task_status(request, task_id):
    """Consulta el estado de una tarea."""
    import httpx

    resp = httpx.get(f"http://localhost:8001/api/v1/tasks/{task_id}")
    return JsonResponse(resp.json())
```

En `urls.py`:

```python
from django.urls import path
from . import views

urlpatterns = [
    path("add/<int:a>/<int:b>/", views.enqueue_add),
    path("hello/<str:name>/", views.enqueue_hello),
    path("task/<uuid:task_id>/", views.task_status),
]
```

### Ejecutar

**Terminal 1** — Servidor Lapinq con worker:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/lapinq \
python -m lapinq server --worker --port 8001
```

**Terminal 2** — Servidor de desarrollo Django:

```bash
python manage.py runserver 0.0.0.0:8000
```

### Probar el Flujo

```bash
# Encolar add(10, 20)
curl http://localhost:8000/add/10/20/
# → {"task_id": "abc-1234-..."}

# Consultar resultado (vía API de Lapinq)
curl http://localhost:8001/api/v1/tasks/abc-1234-.../result
# → {"id": "abc-1234-...", "status": "completed", "result": "30", ...}

# Encolar saludo
curl http://localhost:8000/hello/Mundo/
# → {"task_id": "def-5678-..."}

# Consultar resultado
curl http://localhost:8001/api/v1/tasks/def-5678-.../result
# → {"id": "def-5678-...", "status": "completed", "result": "\"Hola, Mundo!\"", ...}
```

### Resultados Esperados

| Tarea | Entrada | Resultado |
|-------|---------|-----------|
| `add(10, 20)` | `10, 20` | `30` |
| `hello("Mundo", greeting="Hola")` | `"Mundo"` | `"Hola, Mundo!"` |

---

## Usar la Librería Cliente Directamente

No necesitas FastAPI ni Django — la librería cliente funciona desde cualquier script Python:

```python
from lapinq.client import TaskQueue

tq = TaskQueue(server_url="http://localhost:8001")


@tq.task(name="greet")
def greet(name: str) -> str:
    return f"Hello, {name}!"


# Encolar una tarea. La función también funciona normalmente:
result = greet.queue("World")
task_id = result.json()["task_id"]
```

Para código asíncrono:

```python
from lapinq.client import AsyncTaskQueue

tq = AsyncTaskQueue(server_url="http://localhost:8001")


@tq.task(name="greet_async")
async def greet_async(name: str) -> str:
    return f"Hello, {name}!"


# En un contexto async:
result = await greet_async.aqueue("World")
```

---

## Patrones Comunes

### Worker Inline (Configuración Más Simple)

Combina servidor y worker en un solo proceso:

```bash
python -m lapinq server --worker --port 8001
```

### Servidor y Worker Separados (Producción)

Ejecuta el servidor sin worker:

```bash
python -m lapinq server --port 8001
```

Ejecuta uno o más workers Python:

```bash
python -m lapinq worker --concurrency 4
```

O el worker Rust (requiere compilación):

```bash
lapinq-worker --database-url $DATABASE_URL --concurrency 4
```

### Consultar Resultados de Tareas

Usa el endpoint dedicado de resultados:

```bash
curl http://localhost:8001/api/v1/tasks/<task_id>/result
```

Devuelve el resultado inmediatamente si la tarea terminó, o `"error": "task not finished"` con el estado actual.
