# Despliegue

## Docker Compose (Un contenedor — Servidor + Worker)

El despliegue más simple ejecuta servidor y worker en un solo proceso:

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

## Docker Compose (Worker separado — Producción)

Para producción, escala el worker independientemente:

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

## Consideraciones de Producción

### PostgreSQL

- Usa un servicio gestionado (RDS, Cloud SQL, etc.) para producción
- Activa connection pooling (PgBouncer) para alta concurrencia
- Configura `max_connections` adecuadamente

### Configuración del Worker

- `--concurrency`: Ajusta a los núcleos de CPU (normalmente 2-4 por worker)
- `--task-timeout`: Evita tareas sin fin (por defecto 300s)
- `--cleanup-interval`: Configura a 300s o más para limpieza TTL
- Ejecuta múltiples réplicas del worker para alto rendimiento

### Escalado

Cada worker reclama tareas independientemente usando `FOR UPDATE SKIP LOCKED`, por lo que escalan horizontalmente sin coordinación.

```bash
# Ejecuta múltiples workers Rust
lapinq-worker --database-url $DATABASE_URL --concurrency 4
lapinq-worker --database-url $DATABASE_URL --concurrency 4
```

### Autenticación y Rate Limiting

```bash
# Activar autenticación por API key
LAGOMORPH_API_KEY=mi-clave-secreta python -m lapinq server

# Activar rate limiting (60 peticiones/min por IP)
LAGOMORPH_RATE_LIMIT=60 python -m lapinq server
```

### Monitoreo

- Dashboard en `http://localhost:8001`
- Health check: `GET /health`
- Métricas Prometheus: `GET /metrics`
- Estadísticas de colas: `GET /api/queues`
- DLQ (Dead Letter Queue): `GET /api/tasks/failed`
