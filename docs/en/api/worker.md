# Worker API Reference

## Python Workers

### `run_worker(database_url, concurrency, poll_interval, task_timeout)`

Standalone Python worker. Creates its own database connection pool and runs a main loop claiming and executing tasks via subprocess.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_url` | `str \| None` | `DATABASE_URL` env var | PostgreSQL connection URL |
| `concurrency` | `int` | `4` | Max simultaneous tasks |
| `poll_interval` | `float` | `0.1` | Seconds between DB polls |
| `task_timeout` | `int` | `300` | Task timeout in seconds |

Graceful shutdown on `SIGTERM`/`SIGINT`. Sends heartbeat every 15s.

### `run_worker_inline(storage, concurrency, poll_interval, task_timeout)`

Inline worker that runs in the same event loop as the server. Takes an existing `Storage` instance and executes tasks in-process using the Rust executor (PyO3) for sync functions.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `storage` | `Storage` | required | Shared database connection pool |
| `concurrency` | `int` | `4` | Max simultaneous tasks |
| `poll_interval` | `float` | `0.1` | Seconds between DB polls |
| `task_timeout` | `int` | `300` | Task timeout in seconds |

### CLI — Python Worker

```bash
python -m lagomorph worker \
  --database-url postgresql://user:pass@localhost:5432/db \
  --concurrency 4 \
  --poll-interval 0.1 \
  --task-timeout 300
```

### CLI — Inline Worker (with server)

```bash
python -m lagomorph server --worker --port 8001
```

## Rust Worker

### CLI

```bash
lagomorph-worker \
  --database-url postgresql://user:pass@localhost:5432/db \
  --concurrency 4 \
  --poll-interval 0.1 \
  --task-timeout 300
```

| Flag | Env | Default | Description |
|------|-----|---------|-------------|
| `--database-url` | `DATABASE_URL` | `postgresql://localhost:5432/lagomorph` | PostgreSQL connection URL |
| `--concurrency` | | `4` | Max simultaneous tasks |
| `--poll-interval` | | `0.1` | Seconds between DB polls |
| `--task-timeout` | | `300` | Task timeout in seconds |

The Rust worker connects directly to PostgreSQL, claims tasks using `FOR UPDATE SKIP LOCKED`, and executes each task by spawning `python -m lagomorph execute <task_id>` as a subprocess. It handles retries with exponential backoff (10, 30, 60, 300, 600 seconds).

## Rust Executor (Embedded)

The Python worker optionally uses the Rust task executor via PyO3 for synchronous task functions, avoiding subprocess overhead. Imported as:

```python
from lagomorph._worker import execute_task_inline

result = execute_task_inline(task_data)
```

The Rust executor:
- Imports the Python module and calls the function directly
- Returns the result as a JSON string
- Rejects async functions (handled by the Python fallback)
- Is automatically used by `run_worker_inline` when available

## Task Executor

### `execute_task(task_id)`

Internal function executed as a subprocess for each task. Connects to PostgreSQL, reads the task, imports the module, calls the function, and prints the result to stdout.

### CLI

```bash
python -m lagomorph execute <task_id>
```
