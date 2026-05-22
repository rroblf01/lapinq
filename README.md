# Lagomorph 🐇

**A lightweight task queue with PostgreSQL backend — replacing Celery + RabbitMQ with a single container.**

[![CI](https://github.com/ricardorobles/lagomorph/actions/workflows/ci.yml/badge.svg)](https://github.com/ricardorobles/lagomorph/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/lagomorph)](https://pypi.org/project/lagomorph/)
[![Python](https://img.shields.io/pypi/pyversions/lagomorph)](https://pypi.org/project/lagomorph/)
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
from lagomorph import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001", queue_name="video")

@tasks.task(name="procesar_video")
def procesar_video(video_id: int, codec: str):
    print(f"Processing video {video_id} with {codec}")

# Enqueue the task — runs on the worker
procesar_video(video_id=1, codec="h264")
```

## Installation

```bash
pip install lagomorph
```

Or from source:

```bash
git clone https://github.com/ricardorobles/lagomorph.git
cd lagomorph
pip install maturin
maturin develop
```

## Usage

### 1. Start PostgreSQL

```bash
docker run -d --name lagomorph-pg \
  -e POSTGRES_USER=lagomorph \
  -e POSTGRES_PASSWORD=secret \
  -e POSTGRES_DB=lagomorph \
  -p 5432:5432 \
  postgres:16-alpine
```

### 2. Start the server

```bash
lagomorph server --host 0.0.0.0 --port 8001
```

### 3. Start a worker

```bash
# Python worker (development)
lagomorph worker --concurrency 4

# Or Rust worker (production, ~20x faster polling)
lagomorph-worker --database-url postgresql://lagomorph:secret@localhost:5432/lagomorph --concurrency 4
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

Full documentation is available at **[https://ricardorobles.github.io/lagomorph](https://ricardorobles.github.io/lagomorph)**

## Docker

```bash
docker compose up -d
```

This starts:
- **PostgreSQL** — database engine
- **Server** — lagomorph REST API + dashboard
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

### Phase 4 — Testing & documentation
- [ ] Tests for `execute.py` (100% uncovered)
- [ ] Tests for `worker.py` main loop
- [ ] Tests for CLI argument parsing
- [ ] Rust worker integration tests against real PostgreSQL
- [ ] Document DB schema, env vars, error codes, task lifecycle
- [ ] Real-world example projects in `examples/`

---

## License

MIT
