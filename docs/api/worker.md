# Worker API Reference

## Python Worker

### `run_worker(database_url, concurrency, poll_interval, task_timeout)`

Start the native Python worker.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_url` | `str \| None` | `DATABASE_URL` env var | PostgreSQL connection URL |
| `concurrency` | `int` | `4` | Max simultaneous tasks |
| `poll_interval` | `float` | `0.1` | Seconds between DB polls |
| `task_timeout` | `int` | `300` | Task timeout in seconds |

### CLI

```bash
python -m lagomorph worker --database-url postgresql://... --concurrency 4
```

## Rust Worker

### CLI

```bash
lagomorph-worker --database-url postgresql://... --concurrency 4 --poll-interval 0.1 --task-timeout 300
```

| Flag | Env | Default | Description |
|------|-----|---------|-------------|
| `--database-url` | `DATABASE_URL` | `postgresql://localhost:5432/lagomorph` | PostgreSQL connection URL |
| `--concurrency` | | `4` | Max simultaneous tasks |
| `--poll-interval` | | `0.1` | Seconds between DB polls |
| `--task-timeout` | | `300` | Task timeout in seconds |

## Task Executor

### `execute_task(task_id)`

Internal function that executes a task by ID. Reads task data from PostgreSQL, imports the module, and calls the function.

### CLI

```bash
python -m lagomorph execute <task_id>
```

This is called by the worker for each task.
