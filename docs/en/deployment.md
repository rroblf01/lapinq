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

#### API Key (programmatic access)

```bash
LAPINQ_API_KEY=my-secret-key python -m lapinq server
```

All `/api/*` routes require `X-API-Key` header.

#### Dashboard Authentication

The dashboard uses session-based auth. A default admin user `lapinq`/`lapinq` is created automatically on first startup.

Set a fixed session secret to persist sessions across restarts:

```bash
LAPINQ_SESSION_SECRET=your-secret-key python -m lapinq server
```

Without this, a random secret is generated each startup, invalidating all active sessions.

#### User Roles

- **Admin**: Full access — view dashboard, delete tasks, cancel/requeue, create users, manage permissions.
- **User**: Read-only by default — can view the dashboard and change own password. Admins can grant per-queue permissions (delete, cancel) as needed.

#### Rate Limiting

```bash
LAPINQ_RATE_LIMIT=60 python -m lapinq server
```

Limits requests per IP per minute on `/api/*` routes

### Monitoring

- Dashboard at `http://localhost:8001`
- Health check: `GET /health`
- Prometheus metrics: `GET /metrics`
- Queue stats: `GET /api/v1/queues`
- DLQ (Dead Letter Queue): `GET /api/v1/tasks/failed`
