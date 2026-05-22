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
)
```

### AsyncTaskQueue

```python
from lapinq import AsyncTaskQueue

tasks = AsyncTaskQueue(
    server_url="http://worker:8001",
    queue_name="default",
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

Encolar envía un HTTP POST al servidor y retorna inmediatamente:

```python
# Cliente síncrono
respuesta = enviar_email.queue(to="user@example.com", subject="Hola", body="Mundo")
task_id = respuesta.json()["task_id"]

# Cliente asíncrono
respuesta = await enviar_email.aqueue(to="user@example.com", subject="Hola", body="Mundo")
task_id = respuesta.json()["task_id"]
```

### Parámetros de Tarea

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `scheduled_at` | `str` (ISO 8601) | Retrasar ejecución hasta esta fecha |
| `max_retries` | `int` | Máx. reintentos al fallar (por defecto 3) |
| `priority` | `int` | Valores más altos se ejecutan primero (defecto 0) |
| `ttl_seconds` | `int` | Autoeliminar tarea tras N segundos; `0` = no persistir |

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
curl -X POST http://localhost:8001/api/enqueue \
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
curl "http://localhost:8001/api/tasks?limit=10&status=pending&queue=default"
```

### Estadísticas de colas

```bash
curl http://localhost:8001/api/queues
```

### Obtener una tarea

```bash
curl http://localhost:8001/api/tasks/<task_id>
```

### Cancelar una tarea pendiente

```bash
curl -X DELETE http://localhost:8001/api/tasks/<task_id>
```

### Reencolar una tarea fallida

```bash
curl -X POST http://localhost:8001/api/tasks/<task_id>/requeue
```

### Listar tareas fallidas (DLQ)

```bash
curl http://localhost:8001/api/tasks/failed
```

### Health check

```bash
curl http://localhost:8001/health
```

### Métricas Prometheus

```bash
curl http://localhost:8001/metrics
```

## Dashboard

Abre [http://localhost:8001](http://localhost:8001) en tu navegador.

Características:
- **Actualizaciones en tiempo real**: Conexión WebSocket que envía cambios al instante (respaldado por `LISTEN`/`NOTIFY` de PostgreSQL)
- **Tarjetas de cola**: Conteos de activas/pendientes/completadas/fallidas por cola
- **Tabla de tareas**: ID, nombre, cola, args, resultado, error, estado y TTL restante
- **Filtros**: Cola, estado, ID de tarea, contenido de args, resultado y error
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
