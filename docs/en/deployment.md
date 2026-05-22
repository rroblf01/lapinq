# Deployment

## Docker Compose (Single-container — Server + Worker)

The simplest deployment runs server and worker in one process:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: lapinq
      POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
      POSTGRES_DB: lapinq
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lapinq"]

  lapinq:
    build:
      context: .
      dockerfile: Dockerfile.lapinq
    command: python -m lapinq server --worker --cleanup-interval 300 --port 8001
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://lapinq:${DB_PASSWORD:-changeme}@db:5432/lapinq
    depends_on:
      db:
        condition: service_healthy

volumes:
  postgres_data:
```

## Docker Compose (Separate worker — Production)

For production, scale the worker independently:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: lapinq
      POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
      POSTGRES_DB: lapinq
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lapinq"]

  lapinq:
    build:
      context: .
      dockerfile: Dockerfile.lapinq
    command: python -m lapinq server --port 8001
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://lapinq:${DB_PASSWORD:-changeme}@db:5432/lapinq
    depends_on:
      db:
        condition: service_healthy

  worker:
    build:
      context: .
      dockerfile: Dockerfile.lapinq
    command: lapinq-worker --database-url postgresql://lapinq:${DB_PASSWORD:-changeme}@db:5432/lapinq --concurrency 4
    environment:
      - DATABASE_URL=postgresql://lapinq:${DB_PASSWORD:-changeme}@db:5432/lapinq
    deploy:
      replicas: 2
    depends_on:
      db:
        condition: service_healthy

volumes:
  postgres_data:
```

## Dockerfile.lapinq

```dockerfile
FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/ricardorobles/lapinq:latest /usr/local/bin/lapinq-worker /usr/local/bin/
COPY requirements.txt .
RUN pip install --no-cache-dir lapinq

COPY . .
```

## Production Considerations

### PostgreSQL

- Use a managed PostgreSQL service (RDS, Cloud SQL, etc.) for production
- Enable connection pooling (PgBouncer) for high concurrency
- Set `max_connections` appropriately

### Worker Configuration

- `--concurrency`: Match your CPU cores (typically 2-4 per worker)
- `--task-timeout`: Prevent runaway tasks (default 300s)
- `--cleanup-interval`: Set to 300s or more for TTL cleanup
- Run multiple worker replicas for high throughput

### Scaling

Each worker independently claims tasks using `FOR UPDATE SKIP LOCKED`, so they scale horizontally without coordination.

```bash
# Run multiple Rust workers
lapinq-worker --database-url $DATABASE_URL --concurrency 4
lapinq-worker --database-url $DATABASE_URL --concurrency 4
```

### Auth & Rate Limiting

```bash
# Enable API key auth
LAGOMORPH_API_KEY=my-secret-key python -m lapinq server

# Enable rate limiting (60 requests/min per IP)
LAGOMORPH_RATE_LIMIT=60 python -m lapinq server
```

### Monitoring

- Dashboard at `http://localhost:8001`
- Health check: `GET /health`
- Prometheus metrics: `GET /metrics`
- Queue stats: `GET /api/queues`
- DLQ (Dead Letter Queue): `GET /api/tasks/failed`
