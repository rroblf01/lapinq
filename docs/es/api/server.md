# Referencia de la API del Servidor

## `create_app(database_url, api_key, rate_limit, worker, ...)`

Crea una aplicación Starlette ASGI con la API REST, dashboard y worker inline opcional.

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `database_url` | `str` | `"postgresql://localhost:5432/lagomorph"` | URL de conexión PostgreSQL |
| `api_key` | `str \| None` | `None` | API key para el middleware de autenticación |
| `rate_limit` | `int` | `0` | Máx. peticiones/min por IP (`0` = desactivado) |
| `worker` | `bool` | `False` | Ejecutar worker inline en el mismo proceso |
| `worker_concurrency` | `int` | `4` | Concurrencia del worker inline |
| `worker_poll_interval` | `float` | `0.1` | Intervalo de sondeo a BD (segundos) |
| `worker_timeout` | `int` | `300` | Timeout de tarea (segundos) |
| `cleanup_interval` | `float` | `0` | Intervalo de limpieza TTL (`0` = desactivado) |

## Endpoints

### `POST /api/enqueue`

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
    "ttl_seconds": 86400
}
```

**Respuesta:** `201 Created`

```json
{"task_id": "uuid-here"}
```

Si `ttl_seconds` es `0`, la tarea no se persiste:

```json
{"task_id": null, "ttl_seconds": 0}
```

### `GET /api/queues`

Estadísticas de colas — conteos de pendientes/ejecutándose/completadas/fallidas por cola.

**Respuesta:** `200 OK`

### `GET /api/tasks`

Listar tareas.

| Parámetro query | Por defecto | Descripción |
|-----------------|-------------|-------------|
| `queue` | — | Filtrar por nombre de cola |
| `status` | — | Filtrar por estado (`pending`, `running`, `completed`, `failed`) |
| `limit` | `50` | Máx. resultados |

### `GET /api/tasks/failed`

Listar tareas fallidas (Dead Letter Queue).

| Parámetro query | Por defecto | Descripción |
|-----------------|-------------|-------------|
| `queue` | — | Filtrar por nombre de cola |
| `limit` | `50` | Máx. resultados |

### `GET /api/tasks/{id}`

Obtener una tarea por ID.

**Respuesta:** `200 OK` con detalles completos, o `404 Not Found`.

### `DELETE /api/tasks/{id}`

Cancelar una tarea pendiente (la elimina).

**Respuesta:** `200 OK` o `404 Not Found`.

### `POST /api/tasks/{id}/requeue`

Reencolar una tarea fallida a estado `pending`.

**Respuesta:** `200 OK` o `404 Not Found` (si la tarea no está fallida).

### `GET /health`

Health check. Devuelve `{"status": "ok", "database": "connected"}`.

### `GET /metrics`

Métricas en formato Prometheus:

```
# HELP lagomorph_tasks Task counts by queue and status
# TYPE lagomorph_tasks gauge
lagomorph_tasks{queue="default",status="pending"} 5
lagomorph_tasks{queue="default",status="running"} 2
lagomorph_tasks{queue="default",status="completed"} 100
lagomorph_tasks{queue="default",status="failed"} 1
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

Configura la variable de entorno `LAGOMORPH_API_KEY` o pasa `api_key` a `create_app()`. Todas las rutas `/api/*` requieren la cabecera `X-API-Key` (excepto `OPTIONS`). El dashboard y health check son públicos.

### RateLimitMiddleware

Configura `LAGOMORPH_RATE_LIMIT` o pasa `rate_limit` a `create_app()`. Limita peticiones por IP por minuto en rutas `/api/*`.

## CLI

```bash
python -m lagomorph server \
  --host 0.0.0.0 \
  --port 8001 \
  --database-url postgresql://user:pass@localhost:5432/db \
  --worker \
  --worker-concurrency 4 \
  --cleanup-interval 300
```
