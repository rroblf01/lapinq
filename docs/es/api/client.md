# Referencia de la API del Cliente

## `TaskQueue`

Cliente síncrono para definir y encolar tareas.

### `__init__(server_url, queue_name, timeout)`

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `server_url` | `str` | `"http://127.0.0.1:8001"` | URL del servidor lapinq |
| `queue_name` | `str` | `"default"` | Nombre de cola por defecto |
| `timeout` | `float` | `30.0` | Timeout de petición HTTP en segundos |

### `task(name=None, queue_name=None, scheduled_at=None, max_retries=None, priority=0, ttl_seconds=None)`

Decorador que registra una función como tarea. Se puede usar con o sin paréntesis.

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `name` | `str \| None` | Nombre de la función | Nombre explícito de la tarea |
| `queue_name` | `str \| None` | De `__init__` | Cola donde encolar |
| `scheduled_at` | `str \| None` | `None` | Datetime ISO 8601 para ejecución retardada |
| `max_retries` | `int \| None` | `3` | Máx. reintentos al fallar |
| `priority` | `int` | `0` | Mayor = se ejecuta primero |
| `ttl_seconds` | `int \| None` | `None` | Autoeliminar tarea tras N segundos; `0` = no persistir |

La función decorada:
- Sigue siendo invocable como la función original
- Obtiene un método `.queue()` para encolar la tarea
- Obtiene un atributo `.task_name`

### `close()`

Cierra la conexión HTTP subyacente.

## `AsyncTaskQueue`

Cliente asíncrono. Misma interfaz que `TaskQueue` pero usa `httpx.AsyncClient`.

### `__init__(server_url, queue_name, timeout)`

Mismos parámetros que `TaskQueue`.

### `task(name=None, queue_name=None, scheduled_at=None, max_retries=None, priority=0, ttl_seconds=None)`

Mismos parámetros que `TaskQueue`. Añade una corrutina `.aqueue()` a la función decorada.

### `async close()`

Cierra la conexión HTTP asíncrona subyacente.

## Ejemplos

```python
from lapinq import TaskQueue, AsyncTaskQueue

# Cliente síncrono
tasks = TaskQueue(server_url="http://localhost:8001")

@tasks.task(name="tarea_sync")
def tarea_sync(x: int):
    return x * 2

respuesta = tarea_sync.queue(x=42)
task_id = respuesta.json()["task_id"]

# Cliente asíncrono
async_tasks = AsyncTaskQueue(server_url="http://localhost:8001")

@async_tasks.task(name="tarea_async")
async def tarea_async(x: int):
    return x * 2

respuesta = await tarea_async.aqueue(x=42)
task_id = respuesta.json()["task_id"]
await async_tasks.close()
```
