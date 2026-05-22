# Despliegue

## Docker Compose (Un contenedor — Servidor + Worker)

El despliegue más simple ejecuta servidor y worker en un solo proceso:

```yaml
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
      test: ["CMD-SHELL", "pg_isready -U lagomorph"]

  lagomorph:
    build:
      context: .
      dockerfile: Dockerfile.lagomorph
    command: python -m lagomorph server --worker --cleanup-interval 300 --port 8001
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://lagomorph:${DB_PASSWORD:-changeme}@db:5432/lagomorph
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
      POSTGRES_USER: lagomorph
      POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
      POSTGRES_DB: lagomorph
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lagomorph"]

  lagomorph:
    build:
      context: .
      dockerfile: Dockerfile.lagomorph
    command: python -m lagomorph server --port 8001
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
    deploy:
      replicas: 2
    depends_on:
      db:
        condition: service_healthy

volumes:
  postgres_data:
```

## Dockerfile.lagomorph

```dockerfile
FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/ricardorobles/lagomorph:latest /usr/local/bin/lagomorph-worker /usr/local/bin/
COPY requirements.txt .
RUN pip install --no-cache-dir lagomorph

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
lagomorph-worker --database-url $DATABASE_URL --concurrency 4
lagomorph-worker --database-url $DATABASE_URL --concurrency 4
```

### Autenticación y Rate Limiting

```bash
# Activar autenticación por API key
LAGOMORPH_API_KEY=mi-clave-secreta python -m lagomorph server

# Activar rate limiting (60 peticiones/min por IP)
LAGOMORPH_RATE_LIMIT=60 python -m lagomorph server
```

### Monitoreo

- Dashboard en `http://localhost:8001`
- Health check: `GET /health`
- Métricas Prometheus: `GET /metrics`
- Estadísticas de colas: `GET /api/queues`
- DLQ (Dead Letter Queue): `GET /api/tasks/failed`
