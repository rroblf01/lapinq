# Lagomorph 🐇

**A lightweight task queue with PostgreSQL backend — replacing Celery + RabbitMQ with a single container.**

[![CI](https://github.com/ricardorobles/lapinq/actions/workflows/ci.yml/badge.svg)](https://github.com/ricardorobles/lapinq/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/lapinq)](https://pypi.org/project/lapinq/)
[![Python](https://img.shields.io/pypi/pyversions/lapinq)](https://pypi.org/project/lapinq/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## Why Lagomorph?

Celery + RabbitMQ is powerful but heavyweight for many projects. Lagomorph replaces both with a **single container**:

- **No separate broker** — PostgreSQL handles both storage and queueing
- **No separate worker daemon** — Python or Rust worker built in
- **Real-time dashboard** — Monitor queues and tasks out of the box
- **Configurable concurrency** — Control exactly how many tasks run simultaneously

## Quick Start

```python
from lapinq import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001", queue_name="video")

@tasks.task(name="procesar_video")
def procesar_video(video_id: int, codec: str):
    print(f"Processing video {video_id} with {codec}")

# Enqueue the task — runs on the worker
procesar_video(video_id=1, codec="h264")
```

## Installation

```bash
pip install lapinq
```

Or from source:

```bash
git clone https://github.com/ricardorobles/lapinq.git
cd lapinq
pip install maturin
maturin develop
```

## Usage

### 1. Start PostgreSQL

```bash
docker run -d --name lapinq-pg \
  -e POSTGRES_USER=lapinq \
  -e POSTGRES_PASSWORD=secret \
  -e POSTGRES_DB=lapinq \
  -p 5432:5432 \
  postgres:16-alpine
```

### 2. Start the server

```bash
lapinq server --host 0.0.0.0 --port 8001
```

### 3. Start a worker

```bash
# Python worker (development)
lapinq worker --concurrency 4

# Or Rust worker (production, ~20x faster polling)
lapinq-worker --database-url postgresql://lapinq:secret@localhost:5432/lapinq --concurrency 4
```

### 4. Open the dashboard

Visit **http://localhost:8001/dashboard** to monitor queues and tasks in real time.

## Architecture

```
┌──────────────┐     HTTP      ┌──────────────────┐     SQL      ┌────────────┐
│  Web App     │ ──────────►   │  Lagomorph       │ ─────────►   │ PostgreSQL │
│  (FastAPI/   │               │  Server          │              │            │
│   Django)    │               │  (Starlette)     │              │  Tasks     │
│              │               │  + Dashboard     │              │            │
└──────────────┘               └────────┬─────────┘              └─────▲──────┘
                                         │                              │
                                         │  spawns                      │ polls
                                         ▼                              │
                                ┌──────────────────┐                    │
                                │  Worker           │───────────────────►│
                                │  (Rust or Python) │  FOR UPDATE
                                │                   │  SKIP LOCKED
                                └──────────────────┘
```

## Features

| Feature | Status |
|---------|--------|
| `@tasks.task()` decorator API | ✅ |
| PostgreSQL queue storage | ✅ |
| REST API for task management | ✅ |
| Real-time HTMX dashboard | ✅ |
| Python native worker | ✅ |
| Rust worker (high performance) | ✅ |
| Configurable concurrency | ✅ |
| Task timeout | ✅ |
| Task cancellation | ✅ |
| Multiple queues | ✅ |
| CORS support | ✅ |
| Graceful shutdown | ✅ |
| Docker Compose | ✅ |
| GitHub Actions CI/CD | ✅ |
| MkDocs documentation | ✅ |

## Documentation

Full documentation is available at **[https://ricardorobles.github.io/lapinq](https://ricardorobles.github.io/lapinq)**

## Docker

```bash
docker compose up -d
```

This starts:
- **PostgreSQL** — database engine
- **Server** — lapinq REST API + dashboard
- **Rust Worker** — high-performance task executor (requires `--profile rust`)

## Development

```bash
uv sync
uv run maturin develop
uv run pytest
```

## Roadmap

### Phase 0 — Bug fixes & tech debt ✅
- [x] Fix `except ValueError, AttributeError` syntax (Python 2 relic)
- [x] Remove unused `jinja2` and `itsdangerous` dependencies
- [x] `fail_task()` should store/log the error message, not ignore it
- [x] Add missing `dashboard.png` screenshot or remove the broken reference

### Phase 1 — Core reliability ✅
- [x] **Task history & result storage**: `result`/`error`/`completed_at` columns; `complete_task()` and `fail_task()` UPDATE instead of DELETE
- [x] **Retries with backoff**: `attempts` counter, `max_retries`, exponential backoff (10s, 30s, 60s, 300s, 600s)
- [x] **Stale task reaper**: `recover_stale_tasks()` reclaims `running` tasks past their timeout
- [x] **Dashboard**: shows completed/failed counts per queue
- [x] **Rust worker**: aligned schema and updated `complete_task`/`fail_task` logic

### Phase 2 — Production hardening ✅
- [x] **Authentication**: API key middleware (`X-API-Key` header)
- [x] **Rate limiting**: per-IP request throttling
- [x] **Prometheus metrics**: `/metrics` endpoint for monitoring
- [x] **Structured logging**: JSON logging with `LAGOMORPH_JSON_LOG=1`
- [x] **Configurable pool size**: `max_size` parameter in `Storage.create()`

### Phase 3 — Advanced features ✅
- [x] **Scheduled tasks**: `scheduled_at` support for delayed execution
- [x] **Priority queues**: `priority` column with `ORDER BY priority DESC, created_at`
- [x] **Async client**: `AsyncTaskQueue` for asyncio codebases
- [x] **Dead Letter Queue**: `/api/tasks/failed` list + `/api/tasks/{id}/requeue`
- [x] **Worker heartbeat**: periodic `last_heartbeat` updates every 15s

### Phase 4 — Testing & documentation ✅
- [x] Tests for `execute.py` (success, not-found, function-error via subprocess)
- [x] Tests for `worker.py` main loop (full claim-process-complete cycle)
- [x] Tests for CLI argument parsing (argparse dispatch)
- [x] Document DB schema, env vars, error codes, task lifecycle
- [ ] Rust worker integration tests against real PostgreSQL
- [ ] Real-world example projects in `examples/`

---

## Database Schema

All queue state lives in a single table `lapinq_tasks`:

| Column | Type | Default | Description |
|---|---|---|---|
| `id` | `UUID` | `gen_random_uuid()` | Primary key |
| `queue_name` | `TEXT` | — | Queue this task belongs to |
| `task_name` | `TEXT` | — | Name of the function to call |
| `module_path` | `TEXT` | — | Python module to import |
| `args` | `JSONB` | `[]` | Positional arguments |
| `kwargs` | `JSONB` | `{}` | Keyword arguments |
| `status` | `TEXT` | `pending` | One of: `pending`, `running`, `completed`, `failed` |
| `result` | `TEXT` | — | Serialized return value (completed tasks) |
| `error` | `TEXT` | — | Error message (failed tasks) |
| `attempts` | `INT` | `0` | Number of execution attempts |
| `max_retries` | `INT` | `3` | Max retries before marking as failed |
| `priority` | `INT` | `0` | Higher values claim first |
| `created_at` | `TIMESTAMPTZ` | `now()` | Creation timestamp |
| `scheduled_at` | `TIMESTAMPTZ` | `now()` | Earliest allowed claim time |
| `started_at` | `TIMESTAMPTZ` | — | When a worker claimed the task |
| `completed_at` | `TIMESTAMPTZ` | — | When the task finished (completed or failed) |
| `last_heartbeat` | `TIMESTAMPTZ` | — | Worker periodic heartbeat |
| `worker_id` | `TEXT` | — | Which worker claimed the task |

Key indexes:
- `idx_tasks_status` — filtering by status + created_at order
- `idx_tasks_scheduled` — efficient pending-task polling (`WHERE status = 'pending'`)
- `idx_tasks_pending_priority` — priority-aware claiming

## Environment Variables

| Variable | Default | Used by | Purpose |
|---|---|---|---|
| `DATABASE_URL` | `postgresql://localhost:5432/lapinq` | server, worker, execute | PostgreSQL connection string |
| `LAGOMORPH_API_KEY` | *(none — auth disabled)* | server | Enables `X-API-Key` auth middleware |
| `LAGOMORPH_RATE_LIMIT` | `0` (disabled) | server | Max requests per minute per IP |
| `LAGOMORPH_JSON_LOG` | `0` (text logging) | server, worker, execute | Set to `1` for structured JSON |
| `LAGOMORPH_LOG_LEVEL` | `INFO` | server, worker, execute | Log level override |

## Task Lifecycle

```
enqueue ──► pending ──► running ──► completed
                │                     │
                │                     ├── result captured
                │                     └── status = 'completed'
                │
                └── (scheduled_at in future)
                        └── claimed after scheduled_at

running ──► fail (attempts < max_retries)
                └── pending (scheduled with backoff)

running ──► fail (attempts >= max_retries)
                └── failed (stored with error)

running ──► worker crash / timeout
                └── pending (recovered by stale-task reaper)

failed ──► requeue
                └── pending (reset attempts = 0)
```

Retry backoff schedule: 10s, 30s, 60s, 300s, 600s (cap at 600s).

---

## License

MIT
