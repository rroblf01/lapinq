# Deployment

## Docker Compose

The recommended way to deploy lagomorph is with Docker Compose.

### docker-compose.yml

Create a `docker-compose.yml` in your project:

```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: lagomorph
      POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
      POSTGRES_DB: lagomorph
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lagomorph -d lagomorph"]

  lagomorph:
    build:
      context: .
      dockerfile: Dockerfile.lagomorph
    command: python -m lagomorph server --host 0.0.0.0 --port 8001
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://lagomorph:${DB_PASSWORD:-changeme}@db:5432/lagomorph
    depends_on:
      db:
        condition: service_healthy

  worker:
    build:
      context: .
      dockerfile: Dockerfile.lagomorph
    command: lagomorph-worker --database-url postgresql://lagomorph:${DB_PASSWORD:-changeme}@db:5432/lagomorph --concurrency 4
    environment:
      - DATABASE_URL=postgresql://lagomorph:${DB_PASSWORD:-changeme}@db:5432/lagomorph
    depends_on:
      db:
        condition: service_healthy

volumes:
  postgres_data:
```

### Dockerfile.lagomorph

Create a `Dockerfile.lagomorph` in your project:

```dockerfile
FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/ricardorobles/lagomorph:latest /usr/local/bin/lagomorph-worker /usr/local/bin/
COPY requirements.txt .
RUN pip install --no-cache-dir lagomorph

COPY . .

CMD ["python", "-m", "lagomorph", "server"]
```

## Production Considerations

### PostgreSQL

- Use a managed PostgreSQL service (RDS, Cloud SQL, etc.) for production
- Enable connection pooling (PgBouncer) for high concurrency
- Set `max_connections` appropriately in PostgreSQL config

### Worker Configuration

- Set `--concurrency` to match your CPU cores (typically 2-4 per worker)
- Set `--task-timeout` to prevent runaway tasks (default 300s)
- Run multiple worker replicas for high throughput

### Scaling

```bash
# Run multiple workers
lagomorph-worker --database-url $DATABASE_URL --concurrency 4
lagomorph-worker --database-url $DATABASE_URL --concurrency 4
```

Each worker independently polls the database using `FOR UPDATE SKIP LOCKED`, so they scale horizontally without coordination.

### Monitoring

- Dashboard available at `/dashboard` on the server port
- Health check endpoint: `GET /health`
- Queue stats endpoint: `GET /api/queues`
