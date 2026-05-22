# Getting Started

## Installation

### From PyPI

```bash
pip install lagomorph
```

### From source

```bash
git clone https://github.com/ricardorobles/lagomorph.git
cd lagomorph
pip install maturin
maturin develop
```

## Starting the Server

### Using Docker (recommended)

```bash
docker compose up -d server db
```

### Directly with Python

```bash
# Start PostgreSQL first, then:
python -m lagomorph server --host 0.0.0.0 --port 8001
```

## Starting a Worker

### Python worker (for development)

```bash
python -m lagomorph worker --concurrency 4
```

### Rust worker (for production)

```bash
lagomorph-worker --database-url postgresql://user:pass@localhost:5432/db --concurrency 4
```

## Your First Task

```python
from lagomorph import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001")

@tasks.task(name="hello")
def hello(name: str):
    return f"Hello, {name}!"

# Enqueue the task — executes asynchronously on the worker
hello(name="World")
```
