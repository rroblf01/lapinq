# Referencia de la API del Cliente

## `TaskQueue`

Cliente síncrono para definir y encolar tareas.

### `__init__(server_url, queue_name, timeout, api_key, default_ttl_seconds)`

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `server_url` | `str` | `"http://127.0.0.1:8001"` | URL del servidor lapinq |
| `queue_name` | `str` | `"default"` | Nombre de cola por defecto |
| `timeout` | `float` | `30.0` | Timeout de petición HTTP en segundos |
| `api_key` | `str \| None` | `None` | API key para cabecera `X-API-Key` |
| `default_ttl_seconds` | `float \| None` | `None` | TTL por defecto para tareas sin `ttl_seconds` explícito |

### `task(name=None, queue_name=None, scheduled_at=None, max_retries=None, priority=0, ttl_seconds=None, metadata=None, retry_delay=None, retry_backoff=None, webhook_url=None)`

Decorador que registra una función como tarea. Se puede usar con o sin paréntesis.

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `name` | `str \| None` | Nombre de la función | Nombre explícito de la tarea |
| `queue_name` | `str \| None` | De `__init__` | Cola donde encolar |
| `scheduled_at` | `str \| None` | `None` | Datetime ISO 8601 para ejecución retardada |
| `max_retries` | `int \| None` | `3` | Máx. reintentos al fallar |
| `priority` | `int` | `0` | Mayor = se ejecuta primero |
| `ttl_seconds` | `int \| None` | `None` | Autoeliminar tarea tras N segundos; `0` = no persistir |
| `metadata` | `dict \| None` | `None` | Pares clave-valor arbitrarios almacenados como JSONB |
| `retry_delay` | `float \| None` | `None` | Espera fija entre reintentos (segundos) |
| `retry_backoff` | `bool \| None` | `None` | Backoff exponencial (por defecto `true`) |
| `webhook_url` | `str \| None` | `None` | URL llamada vía POST al completar/fallar |

La función decorada:
- Sigue siendo invocable como la función original
- Obtiene un método `.queue()` que devuelve un objeto `TaskRef`
- Obtiene un atributo `.task_name`

### `batch_enqueue(tasks)`

Encola múltiples tareas en una sola petición.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `tasks` | `list[dict]` | Lista de payloads de tareas |

Devuelve `httpx.Response`.

### `close()`

Cierra la conexión HTTP subyacente.

## `AsyncTaskQueue`

Cliente asíncrono. Misma interfaz que `TaskQueue` pero usa `httpx.AsyncClient`.

### `__init__(server_url, queue_name, timeout, api_key, default_ttl_seconds)`

Mismos parámetros que `TaskQueue`.

### `task(name=None, queue_name=None, scheduled_at=None, max_retries=None, priority=0, ttl_seconds=None, metadata=None, retry_delay=None, retry_backoff=None, webhook_url=None)`

Mismos parámetros que `TaskQueue`. Añade una corrutina `.aqueue()` que devuelve un objeto `TaskRef`.

### `async batch_enqueue(tasks)`

Versión asíncrona de `batch_enqueue`. Devuelve `httpx.Response`.

### `async close()`

Cierra la conexión HTTP asíncrona subyacente.

## `TaskRef`

Devuelto por `.queue()` y `.aqueue()`. Envuelve la respuesta HTTP del servidor.

| Atributo / Método | Descripción |
|--------------------|-------------|
| `.task_id` | UUID de la tarea (o `None` para tareas con TTL cero) |
| `.json()` | Cuerpo de la respuesta como dict |
| `.status_code` | Código de estado HTTP |
| `.wait(timeout=30)` | Sondea hasta que la tarea se complete o expire el timeout (síncrono) |
| `await .awaitait(timeout=30)` | Sondea hasta que la tarea se complete o expire el timeout (asíncrono) |

## Ejemplos

```python
from lapinq import TaskQueue, AsyncTaskQueue

# Cliente síncrono
tasks = TaskQueue(server_url="http://localhost:8001")

@tasks.task(name="tarea_sync")
def tarea_sync(x: int):
    return x * 2

ref = tarea_sync.queue(x=42)
print(ref.task_id)           # "uuid-here"
print(ref.wait(timeout=30))  # {"status": "completed", "result": "84", ...}

# Cliente asíncrono
async_tasks = AsyncTaskQueue(server_url="http://localhost:8001")

@async_tasks.task(name="tarea_async")
async def tarea_async(x: int):
    return x * 2

ref = await tarea_async.aqueue(x=42)
print(ref.task_id)                              # "uuid-here"
result = await ref.awaitait(timeout=30)
print(result["status"])                         # "completed"
await async_tasks.close()
```
