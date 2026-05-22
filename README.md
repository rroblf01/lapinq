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

## License

MIT
