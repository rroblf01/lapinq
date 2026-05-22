# Referencia de la API del Worker

## Workers Python

### `run_worker(database_url, concurrency, poll_interval, task_timeout)`

Worker Python standalone. Crea su propio pool de conexiones y ejecuta un bucle principal reclamando y ejecutando tareas vía subprocesos.

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `database_url` | `str \| None` | variable env `DATABASE_URL` | URL de conexión PostgreSQL |
| `concurrency` | `int` | `4` | Máx. tareas simultáneas |
| `poll_interval` | `float` | `0.1` | Segundos entre sondeos a BD |
| `task_timeout` | `int` | `300` | Timeout de tarea en segundos |

Apagado graceful con `SIGTERM`/`SIGINT`. Envía heartbeat cada 15s.

### `run_worker_inline(storage, concurrency, poll_interval, task_timeout)`

Worker inline que se ejecuta en el mismo event loop que el servidor. Toma una instancia de `Storage` existente y ejecuta tareas en el mismo proceso usando el ejecutor Rust (PyO3) para funciones síncronas.

| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `storage` | `Storage` | requerido | Pool de conexiones compartido |
| `concurrency` | `int` | `4` | Máx. tareas simultáneas |
| `poll_interval` | `float` | `0.1` | Segundos entre sondeos a BD |
| `task_timeout` | `int` | `300` | Timeout de tarea en segundos |

### CLI — Worker Python

```bash
python -m lapinq worker \
  --database-url postgresql://user:pass@localhost:5432/db \
  --concurrency 4 \
  --poll-interval 0.1 \
  --task-timeout 300
```

### CLI — Worker Inline (con servidor)

```bash
python -m lapinq server --worker --port 8001
```

## Worker Rust

### CLI

```bash
lapinq-worker \
  --database-url postgresql://user:pass@localhost:5432/db \
  --concurrency 4 \
  --poll-interval 0.1 \
  --task-timeout 300
```

| Flag | Env | Por defecto | Descripción |
|------|-----|-------------|-------------|
| `--database-url` | `DATABASE_URL` | `postgresql://localhost:5432/lapinq` | URL de conexión PostgreSQL |
| `--concurrency` | | `4` | Máx. tareas simultáneas |
| `--poll-interval` | | `0.1` | Segundos entre sondeos a BD |
| `--task-timeout` | | `300` | Timeout de tarea en segundos |

El worker Rust se conecta directamente a PostgreSQL, reclama tareas usando `FOR UPDATE SKIP LOCKED`, y ejecuta cada tarea lanzando `python -m lapinq execute <task_id>` como subproceso. Maneja reintentos con backoff exponencial (10, 30, 60, 300, 600 segundos).

## Ejecutor Rust (Embebido)

El worker Python usa opcionalmente el ejecutor Rust vía PyO3 para funciones síncronas, evitando la sobrecarga de subprocesos. Se importa como:

```python
from lapinq._worker import execute_task_inline

resultado = execute_task_inline(datos_tarea)
```

El ejecutor Rust:
- Importa el módulo Python y llama a la función directamente
- Devuelve el resultado como string JSON
- Rechaza funciones asíncronas (gestionadas por el fallback Python)
- Es usado automáticamente por `run_worker_inline` cuando está disponible

## Ejecutor de Tareas

### `execute_task(task_id)`

Función interna ejecutada como subproceso para cada tarea. Se conecta a PostgreSQL, lee la tarea, importa el módulo, llama a la función e imprime el resultado en stdout.

### CLI

```bash
python -m lapinq execute <task_id>
```
