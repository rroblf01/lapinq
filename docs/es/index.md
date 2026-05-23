# Lapinq

**Una cola de tareas ligera con backend PostgreSQL — reemplazando Celery + RabbitMQ con un solo contenedor.**

## Características

- **API simple**: Decora tus funciones con `@tasks.task()` para encolarlas
- **Backend PostgreSQL**: Sin necesidad de un broker separado — las tareas se almacenan en PostgreSQL
- **Ejecutor Rust**: Las funciones síncronas se ejecutan vía Rust embebido (PyO3), evitando la sobrecarga de subprocesos
- **Worker integrado**: Ejecuta servidor + worker en un solo proceso con la flag `--worker`
- **Dashboard en tiempo real**: Dashboard vía WebSocket con actualizaciones instantáneas gracias a `LISTEN`/`NOTIFY` de PostgreSQL
- **Soporte TTL**: Configura la expiración de tareas — se eliminan automáticamente tras un TTL configurable
- **Filtros avanzados**: Busca tareas por ID, estado, cola, argumentos, resultado y contenido de error
- **DLQ (Dead Letter Queue)**: Las tareas fallidas están disponibles para inspección y reencolado
- **Métricas Prometheus**: Expone métricas de la cola para monitoreo
- **Concurrencia configurable**: Controla cuántas tareas se ejecutan simultáneamente
- **Worker Rust** (opcional): Binario standalone de alto rendimiento
- **Autenticación y rate limiting**: Autenticación opcional por API key y limitación por IP
- **Paquete PyPI**: Instala con `pip install lapinq`

## Inicio Rápido

```python
from lapinq import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001", queue_name="video")

@tasks.task(name="procesar_video")
def procesar_video(video_id: int, codec: str):
    print(f"Procesando video {video_id} con {codec}")

# Encola la tarea — envía HTTP POST al servidor
respuesta = procesar_video.queue(1, codec="h264")
task_id = respuesta.json()["task_id"]
```

## Arquitectura

```
┌──────────────┐     HTTP      ┌──────────────────┐     SQL      ┌────────────┐
│  App Web     │ ──────────►   │  Servidor        │ ─────────►   │ PostgreSQL │
│  (FastAPI/   │               │  Lapinq          │              │            │
│   Django)    │               │  (Starlette +    │              │  tareas    │
│              │               │   Worker Interno)│              └────────────┘
└──────────────┘               │  - API REST      │
                               │  - Dashboard(WS) │
                               │  - Worker (opt.) │
                               └───────────────────┘
```

O con worker Rust separado para producción:

```
┌──────────────┐     HTTP      ┌──────────────────┐
│  App Web     │ ──────────►   │  Servidor        │ ────┐
│  (FastAPI/   │               │  Lapinq          │     │
│   Django)    │               │  (sin worker)    │     │
│              │               └──────────────────┘     │  SQL
│              │                                         │
└──────────────┘               ┌──────────────────┐     │
                               │  Worker Rust     │ ◄───┘
                               │  (binario        │
                               │   lapinq-     │
                               │   worker)        │
                               └──────────────────┘
```
