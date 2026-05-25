# Referencia de la API del Servidor

## `create_app(database_url, api_key, rate_limit, worker, ...)`

Crea una aplicación Starlette ASGI con la API REST, dashboard y worker inline opcional.

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `database_url` | `str` | `"postgresql://localhost:5432/lapinq"` | URL de conexión PostgreSQL |
| `api_key` | `str \| None` | `None` | API key para el middleware de autenticación |
| `rate_limit` | `int` | `0` | Máx. peticiones/min por IP (`0` = desactivado) |
| `worker` | `bool` | `False` | Ejecutar worker inline en el mismo proceso |
| `worker_concurrency` | `int` | `4` | Concurrencia del worker inline |
| `worker_poll_interval` | `float` | `0.1` | Intervalo de sondeo a BD (segundos) |
| `worker_timeout` | `int` | `300` | Timeout de tarea (segundos) |
| `cleanup_interval` | `float` | `0` | Intervalo de limpieza TTL (`0` = desactivado) |
| `scheduler` | `bool` | `False` | Ejecutar planificador periódico en proceso |
| `scheduler_interval` | `int` | `60` | Intervalo de ejecución del planificador (segundos) |

## Endpoints

### `POST /api/v1/enqueue`

Encola una nueva tarea.

**Cuerpo de la petición:**

```json
{
    "task_name": "mi_tarea",
    "queue_name": "default",
    "module_path": "miapp.tareas",
    "args": [1, 2, 3],
    "kwargs": {"key": "value"},
    "scheduled_at": "2026-06-15T12:00:00Z",
    "max_retries": 3,
    "priority": 5,
    "ttl_seconds": 86400,
    "metadata": {"source": "web", "user_id": 42},
    "retry_delay": 30,
    "retry_backoff": false,
    "webhook_url": "https://miapp.com/webhooks/tarea-completada"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `task_name` | `str` | Nombre de la función de tarea |
| `queue_name` | `str` | Cola donde encolar |
| `module_path` | `str` | Módulo Python a importar |
| `args` | `list` | Argumentos posicionales |
| `kwargs` | `object` | Argumentos nombrados |
| `scheduled_at` | `str` | ISO 8601 para ejecución retardada |
| `max_retries` | `int` | Máx. reintentos (por defecto 3) |
| `priority` | `int` | Mayor = se ejecuta primero (por defecto 0) |
| `ttl_seconds` | `int` | Auto-eliminar tras N segundos; `0` = no persistir |
| `metadata` | `object` | Pares clave-valor JSONB arbitrarios |
| `retry_delay` | `int` | Espera fija entre reintentos (segundos) |
| `retry_backoff` | `bool` | Backoff exponencial (por defecto `true`) |
| `webhook_url` | `str` | URL llamada al completar/fallar la tarea |

**Respuesta:** `201 Created`

```json
{"task_id": "uuid-here"}
```

Si `ttl_seconds` es `0`, la tarea no se persiste:

```json
{"task_id": null, "ttl_seconds": 0}
```

### `POST /api/v1/enqueue/batch`

Encola múltiples tareas en una sola petición (hasta 1000).

**Cuerpo de la petición:**

```json
[
    {"task_name": "add", "queue_name": "batch", "module_path": "miapp.tareas", "args": [1, 2], "max_retries": 0},
    {"task_name": "add", "queue_name": "batch", "module_path": "miapp.tareas", "args": [3, 4], "max_retries": 0}
]
```

**Respuesta:** `201 Created`

```json
{"task_ids": ["uuid-1", "uuid-2"]}
```

### `PATCH /api/v1/tasks/{id}/progress`

Actualiza el progreso de una tarea en ejecución.

**Cuerpo de la petición:**

```json
{
    "progress": 50,
    "message": "Procesando frame 50/100"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `progress` | `int` | Porcentaje de progreso (0–100) |
| `message` | `str` | Descripción opcional del progreso |

**Respuesta:** `200 OK`

### `GET /api/v1/tasks/{id}/result`

Obtiene solo el resultado de una tarea completada.

**Respuesta:** `200 OK`

```json
{"id": "uuid", "status": "completed", "result": "\"done\"", "error": null, "completed_at": "2026-01-01T00:00:00"}
```

Devuelve `{"error": "task not finished"}` con el estado actual si aún no se ha completado.

### `GET /api/v1/queues`

Estadísticas de colas — conteos de pendientes/ejecutándose/completadas/fallidas por cola.

**Respuesta:** `200 OK`

### `GET /api/v1/tasks`

Listar tareas.

| Parámetro query | Por defecto | Descripción |
|-----------------|-------------|-------------|
| `queue` | — | Filtrar por nombre de cola |
| `status` | — | Filtrar por estado (`pending`, `running`, `completed`, `failed`, `cancelled`, `expired`) |
| `limit` | `50` | Máx. resultados |

### `GET /api/v1/tasks/failed`

Listar tareas fallidas (Dead Letter Queue).

| Parámetro query | Por defecto | Descripción |
|-----------------|-------------|-------------|
| `queue` | — | Filtrar por nombre de cola |
| `limit` | `50` | Máx. resultados |

### `GET /api/v1/tasks/{id}`

Obtener una tarea por ID.

**Respuesta:** `200 OK` con detalles completos, o `404 Not Found`.

### `DELETE /api/v1/tasks/{id}`

Cancelar una tarea pendiente (establece estado a `cancelled`).

**Respuesta:** `200 OK` o `404 Not Found`.

### `POST /api/v1/tasks/{id}/requeue`

Reencolar una tarea fallida a estado `pending`.

**Respuesta:** `200 OK` o `404 Not Found` (si la tarea no está fallida).

### `GET /health`

Health check. Devuelve `{"status": "ok", "database": "connected"}`.

### `GET /metrics`

Métricas en formato Prometheus:

```
# HELP lapinq_tasks Task counts by queue and status
# TYPE lapinq_tasks gauge
lapinq_tasks{queue="default",status="pending"} 5
lapinq_tasks{queue="default",status="running"} 2
lapinq_tasks{queue="default",status="completed"} 100
lapinq_tasks{queue="default",status="failed"} 1
```

### `GET /` — Dashboard

Dashboard HTML con actualizaciones en tiempo real vía WebSocket en `/ws`.

### `WebSocket /ws`

Datos del dashboard en tiempo real. El servidor envía JSON con fragmentos HTML `cards` y `table` cada 2 segundos o inmediatamente cuando las tareas cambian (vía `LISTEN`/`NOTIFY` de PostgreSQL).

**Mensajes de filtro Cliente → Servidor:**

```json
{"queue": "video"}
{"id": "3cd39f6d..."}
{"status": "failed"}
{"args": "palabra"}
{"result": "exitoso"}
{"error": "timeout"}
```

## Middleware

### AuthMiddleware

Configura la variable de entorno `LAPINQ_API_KEY` o pasa `api_key` a `create_app()`. Todas las rutas `/api/*` requieren la cabecera `X-API-Key` (excepto `OPTIONS`). El dashboard y health check son públicos.

### RateLimitMiddleware

Configura `LAPINQ_RATE_LIMIT` o pasa `rate_limit` a `create_app()`. Limita peticiones por IP por minuto en rutas `/api/*`.

## CLI

```bash
python -m lapinq server \
  --host 0.0.0.0 \
  --port 8001 \
  --database-url postgresql://user:pass@localhost:5432/db \
  --worker \
  --worker-concurrency 4 \
  --cleanup-interval 300
```
