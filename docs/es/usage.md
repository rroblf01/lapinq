# Guía de Uso

## Cliente TaskQueue

La clase `TaskQueue` es el punto de entrada principal para definir y encolar tareas de forma síncrona.

### Configuración

```python
from lapinq import TaskQueue

tasks = TaskQueue(
    server_url="http://worker:8001",
    queue_name="default",
    timeout=30.0,
    api_key=None,
    default_ttl_seconds=None,
)
```

### AsyncTaskQueue

```python
from lapinq import AsyncTaskQueue

tasks = AsyncTaskQueue(
    server_url="http://worker:8001",
    queue_name="default",
    api_key=None,
    default_ttl_seconds=None,
)
```

### Definiendo Tareas

Las tareas se pueden decorar con o sin paréntesis:

```python
@tasks.task  # sin paréntesis — usa el nombre de la función
def enviar_email(to: str, subject: str, body: str):
    print(f"Enviando email a {to}: {subject}")

@tasks.task(name="procesar_imagen", queue_name="images", priority=10)
def procesar_imagen(image_id: int, quality: int = 80):
    pass

@tasks.task(name="tarea_larga", ttl_seconds=3600)
def tarea_larga(data: str):
    """Tarea se autoelimina 1 hora después de su creación."""
    pass
```

La función decorada sigue siendo invocable como la original:

```python
enviar_email(to="user@example.com", subject="Hola", body="Mundo")  # llama directamente
```

### Encolando Tareas

Encolar envía un HTTP POST al servidor y retorna un `TaskRef`:

```python
# Cliente síncrono — devuelve TaskRef
ref = enviar_email.queue(to="user@example.com", subject="Hola", body="Mundo")
print(ref.task_id)           # "uuid-here"
print(ref.wait(timeout=30))  # sondea hasta completar

# Cliente asíncrono — devuelve TaskRef
ref = await enviar_email.aqueue(to="user@example.com", subject="Hola", body="Mundo")
result = await ref.awaitait(timeout=30)
print(result["status"])
```

### Parámetros de Tarea

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `scheduled_at` | `str` (ISO 8601) | Retrasar ejecución hasta esta fecha |
| `max_retries` | `int` | Máx. reintentos al fallar (por defecto 3) |
| `priority` | `int` | Valores más altos se ejecutan primero (defecto 0) |
| `ttl_seconds` | `int` | Autoeliminar tarea tras N segundos; `0` = no persistir |
| `metadata` | `dict` | Pares clave-valor arbitrarios almacenados como JSONB |
| `retry_delay` | `float` | Espera fija entre reintentos (segundos) |
| `retry_backoff` | `bool` | Backoff exponencial (por defecto `true`) |
| `webhook_url` | `str` | URL llamada vía POST al completar/fallar |

```python
@tasks.task(name="retrasada", scheduled_at="2026-06-15T12:30:00Z")
def tarea_retrasada():
    pass

@tasks.task(name="sin_reintento", max_retries=0)
def tarea_fragil():
    pass

@tasks.task(name="volatil", ttl_seconds=0)
def noop():
    pass  # Esta tarea se descarta inmediatamente
```

## API REST

### Encolar una tarea

```bash
curl -X POST http://localhost:8001/api/v1/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "mi_tarea",
    "queue_name": "default",
    "module_path": "miapp.tareas",
    "args": [1],
    "kwargs": {"key": "value"},
    "priority": 5,
    "max_retries": 3,
    "ttl_seconds": 86400,
    "scheduled_at": "2026-06-15T12:00:00Z"
  }'
```

### Listar tareas

```bash
curl "http://localhost:8001/api/v1/tasks?limit=10&status=pending&queue=default&task_name=procesar"
```

### Estadísticas de colas

```bash
curl http://localhost:8001/api/v1/queues
```

### Obtener una tarea

```bash
curl http://localhost:8001/api/v1/tasks/<task_id>
```

### Cancelar una tarea pendiente

```bash
curl -X DELETE http://localhost:8001/api/v1/tasks/<task_id>
```

### Reencolar una tarea fallida

```bash
curl -X POST http://localhost:8001/api/v1/tasks/<task_id>/requeue
```

### Eliminar tareas en lote por filtro

```bash
curl -X DELETE "http://localhost:8001/api/v1/tasks?status=failed&queue=default"
```

Soporta todos los parámetros de filtro: `queue`, `status`, `task_name`, `args`, `result`, `error`.

### Listar tareas fallidas (DLQ)

```bash
curl http://localhost:8001/api/v1/tasks/failed
```

### Health check

```bash
curl http://localhost:8001/health
```

### Métricas Prometheus

```bash
curl http://localhost:8001/metrics
```

## CLI de Gestión de Tareas

```bash
# Listar tareas
lapinq task list --status pending --limit 20 --json

# Obtener una tarea
lapinq task get <task_id> --json

# Cancelar una tarea pendiente
lapinq task cancel <task_id>

# Reencolar una tarea fallida
lapinq task requeue <task_id>
```

## Planificador Cron

Programa tareas recurrentes usando expresiones cron de 5 campos:

```bash
lapinq server --scheduler --scheduler-interval 60
```

Define los horarios insertando filas en la tabla `lapinq_scheduled_tasks`:

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `UUID` | Clave primaria |
| `task_name` | `TEXT` | Nombre de la función de tarea |
| `module_path` | `TEXT` | Módulo Python a importar |
| `queue_name` | `TEXT` | Cola donde encolar |
| `cron_expression` | `TEXT` | Cron de 5 campos (`min hora dia mes dia_semana`) |
| `args` | `JSONB` | Argumentos posicionales |
| `kwargs` | `JSONB` | Argumentos nombrados |
| `enabled` | `BOOLEAN` | `true` = activo, `false` = saltado |

Ejemplo — ejecuta `mi_tarea.cada_minuto` cada minuto:

```sql
INSERT INTO lapinq_scheduled_tasks
    (task_name, module_path, queue_name, cron_expression, args, kwargs, enabled)
VALUES
    ('cada_minuto', 'miapp.tareas', 'default', '* * * * *', '[]', '{}', true);
```

## Dashboard

Abre [http://localhost:8001](http://localhost:8001) en tu navegador. Inicia sesión con la cuenta admin por defecto (`lapinq`/`lapinq`).

Características:
- **Autenticación por sesión**: El dashboard requiere inicio de sesión. Botón de cerrar sesión en el encabezado.
- **Actualizaciones en tiempo real**: Conexión WebSocket que envía cambios al instante (respaldado por `LISTEN`/`NOTIFY` de PostgreSQL)
- **Tarjetas de cola**: Conteos de activas/pendientes/completadas/fallidas por cola
- **Tabla de tareas**: ID, nombre, cola, args, resultado, error, estado y TTL restante
- **Filtros**: Cola, estado, nombre de tarea, ID, args, resultado y error
- **Cancelar/Reencolar**: Los admins pueden cancelar tareas pendientes o reencolar fallidas
- **Eliminar filtradas**: Los admins pueden eliminar en lote las tareas que coincidan con los filtros actuales
- **Cambiar contraseña**: Cualquier usuario autenticado puede cambiar su propia contraseña
- **Gestión de usuarios** (solo admin): Crear usuarios, cambiar roles, establecer permisos por cola
- **Display TTL**: Muestra tiempo restante antes de autoeliminación o `∞` para tareas permanentes

## Limpieza TTL

Activa la limpieza automática de tareas expiradas:

```bash
python -m lapinq server --worker --cleanup-interval 300
```

Esto elimina las tareas donde `created_at + ttl_seconds < now()` cada 5 minutos.

## Múltiples Colas

```python
video_tasks = TaskQueue(server_url="http://worker:8001", queue_name="video")
audio_tasks = TaskQueue(server_url="http://worker:8001", queue_name="audio")

@video_tasks.task(name="transcodificar")
def transcodificar_video(video_id: int):
    pass

@audio_tasks.task(name="convertir")
def convertir_audio(audio_id: int):
    pass
```
