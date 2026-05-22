# Lagomorph Example

A production-like demo with FastAPI + PostgreSQL + Lagomorph.

## Architecture

```
Browser ──► FastAPI (:8000) ──► Lagomorph Server (:8001) ──► PostgreSQL (:5432)
                                      │
                               Lagomorph Worker
```

1. Browser submits a task via the FastAPI form.
2. FastAPI enqueues it via `AsyncTaskQueue` → HTTP → Lagomorph Server.
3. Lagomorph Server writes the task to PostgreSQL.
4. Lagomorph Worker picks it up, imports `app.tasks`, executes the function, and writes the result back.

## Run

```bash
docker compose up --build
```

Wait for all services to start (watch the logs). Then open http://localhost:8000.

## Available tasks

All live in `app/tasks.py`:

| Function     | Behavior                 | Example args                          |
|-------------|--------------------------|---------------------------------------|
| `send_email`| Simulates sending (2s)   | `["a@b.com","Hi","Hello!"]`           |
| `add`       | Returns a + b            | `[1, 2]`                              |
| `fail`      | Always raises            | `[]`                                  |

## Check task status

After enqueuing, copy the returned `task_id` and paste it into the **Check status** form. Or curl:

```bash
curl http://localhost:8000/status?task_id=<uuid>
```
