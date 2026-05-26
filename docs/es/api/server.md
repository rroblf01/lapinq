# Referencia de la API del Servidor

## `create_app(database_url, api_key, session_secret, rate_limit, worker, ...)`

Crea una aplicación Starlette ASGI con la API REST, dashboard y worker inline opcional.

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `database_url` | `str` | `"postgresql://localhost:5432/lapinq"` | URL de conexión PostgreSQL |
| `api_key` | `str \| None` | `None` | API key para el middleware de la API |
| `session_secret` | `str \| None` | `None` | Secreto para cookies de sesión del dashboard (auto-generado si vacío) |
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
| `task_name` | — | Filtrar por nombre de tarea (ILIKE) |
| `limit` | `50` | Máx. resultados |

### `DELETE /api/v1/tasks`

Eliminar tareas en lote según filtros. Requiere sesión admin o `X-API-Key`.

| Parámetro query | Descripción |
|-----------------|-------------|
| `queue` | Filtrar por nombre de cola |
| `status` | Filtrar por estado |
| `task_name` | Filtrar por nombre de tarea (ILIKE) |
| `args` | Filtrar por contenido de args (ILIKE) |
| `result` | Filtrar por contenido de resultado (ILIKE) |
| `error` | Filtrar por contenido de error (ILIKE) |

**Respuesta:** `200 OK`

```json
{"deleted": 5}
```

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

### `GET /login` — Página de Login

Formulario HTML de inicio de sesión. Muestra "Invalid credentials" si falla. Redirige al dashboard al iniciar sesión correctamente.

### `POST /login`

Login basado en formulario. Acepta `username` y `password`. Establece una cookie de sesión si las credenciales son correctas.

### `GET /logout`

Elimina la cookie de sesión y redirige a `/login`.

### `GET /` — Dashboard

Dashboard HTML con autenticación por sesión y actualizaciones en tiempo real vía WebSocket en `/ws`. El primer usuario se crea automáticamente como `lapinq`/`lapinq` con rol admin.

### `GET /admin/users` — Gestión de Usuarios (solo admin)

Página HTML para crear, editar roles, editar permisos y eliminar usuarios.

### `POST /admin/users`

Crear un nuevo usuario (solo admin). Acepta JSON:

```json
{"username": "nuevo", "password": "secreta", "role": "user"}
```

### `POST /admin/users/{id}/role`

Cambiar el rol de un usuario (solo admin). Acepta JSON:

```json
{"role": "admin"}
```

### `POST /admin/users/{id}/permissions`

Establecer permisos por cola (solo admin). Acepta JSON:

```json
{"queues": {"video": ["delete", "cancel"]}}
```

### `DELETE /admin/users/{id}`

Eliminar un usuario (solo admin).

### `POST /account/password`

Cambiar la propia contraseña. Acepta JSON:

```json
{"current_password": "anterior", "new_password": "nueva"}
```

### `GET /me`

Devuelve la información del usuario actual (id, username, role, permissions).

### `WebSocket /ws`

Datos del dashboard en tiempo real. **El primer mensaje debe ser de autenticación:**

```json
{"type": "auth", "token": "<session-token>"}
```

Después de la autenticación, el servidor envía JSON con fragmentos HTML `cards` y `table` cada 2 segundos o inmediatamente cuando las tareas cambian (vía `LISTEN`/`NOTIFY` de PostgreSQL). La respuesta también incluye un objeto `user` con `role` y `username`.

**Mensajes de filtro Cliente → Servidor:**

```json
{"queue": "video"}
{"id": "3cd39f6d..."}
{"status": "failed"}
{"task_name": "procesar"}
{"args": "palabra"}
{"result": "exitoso"}
{"error": "timeout"}
```

## Middleware

### DashboardAuthMiddleware

Se aplica automáticamente a todas las rutas del dashboard. Verifica la cookie `lapinq_session` en cada petición. Si es inválida o falta para rutas protegidas (`/`, `/ws`, `/admin/*`, `/account/*`), redirige a `/login`. Las rutas `/login`, `/health` y `/metrics` son siempre públicas.

### AuthMiddleware

Configura `LAPINQ_API_KEY` o pasa `api_key` a `create_app()`. Todas las rutas `/api/*` requieren la cabecera `X-API-Key` (excepto `OPTIONS`) o una cookie de sesión válida del dashboard. Esto permite que el JavaScript del dashboard llame a los endpoints de la API sin problemas.

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

El secreto de sesión se lee de la variable de entorno `LAPINQ_SESSION_SECRET`. Si no se establece, se genera un secreto aleatorio en cada inicio (invalida todas las sesiones existentes al reiniciar). Establece un valor fijo en producción:

```bash
LAPINQ_SESSION_SECRET=tu-clave-secreta python -m lapinq server
```
