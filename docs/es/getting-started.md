# Primeros Pasos

## Instalación

### Desde PyPI

```bash
pip install lapinq
```

### Desde el código fuente

```bash
git clone https://github.com/ricardorobles/lapinq.git
cd lapinq
pip install maturin
maturin develop
```

## Iniciar PostgreSQL

```bash
docker run -d --name lapinq-db \
  -e POSTGRES_USER=lapinq \
  -e POSTGRES_PASSWORD=lapinq \
  -e POSTGRES_DB=lapinq \
  -p 5432:5432 \
  postgres:16-alpine
```

## Iniciar Servidor + Worker Integrado (más simple)

Ejecuta el servidor HTTP y el worker de tareas en un solo proceso:

```bash
python -m lapinq server --worker --port 8001
```

Esta es la forma más fácil de empezar. El worker interno ejecuta las tareas en el mismo proceso usando el ejecutor Rust (PyO3) para funciones síncronas.

## Iniciar Servidor con Worker Separado

### Terminal 1 — Servidor:

```bash
python -m lapinq server --port 8001
```

### Terminal 2 — Worker Python:

```bash
python -m lapinq worker --concurrency 4
```

### Terminal 2 — Worker Rust (producción):

```bash
lapinq-worker --database-url postgresql://lapinq:lapinq@localhost:5432/lapinq --concurrency 4
```

## Dashboard

Abre [http://localhost:8001](http://localhost:8001) en tu navegador. El dashboard muestra estadísticas de las colas y tareas recientes con actualizaciones en tiempo real vía WebSocket.

El dashboard está protegido por autenticación por sesión. En el primer inicio el servidor crea un usuario administrador por defecto:

- **Usuario:** `lapinq`
- **Contraseña:** `lapinq`

Después de iniciar sesión, los administradores pueden crear usuarios adicionales, cambiar contraseñas y gestionar permisos desde la página "Manage Users".

## Tu Primera Tarea

```python
from lapinq import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001")

@tasks.task(name="saludo")
def saludar(nombre: str):
    return f"¡Hola, {nombre}!"

# Encola — devuelve un TaskRef
ref = saludar.queue(nombre="Mundo")
print(ref.task_id)  # "uuid-..."
print(ref.wait(timeout=30))  # sondea el resultado
```

## TTL de Tareas (Time To Live)

Las tareas expiran automáticamente después de un tiempo configurable. Establece `ttl_seconds` al encolar.

### Conservar por 1 día (86400s)

```python
ref = saludar.queue(nombre="Mundo", ttl_seconds=86400)
```

### Conservar por 1 minuto (60s)

```python
ref = saludar.queue(nombre="Mundo", ttl_seconds=60)
```

### No persistir (0 = sin TTL, la tarea permanece hasta completarse o archivarse)

```python
ref = saludar.queue(nombre="Mundo", ttl_seconds=0)
```

> `ttl_seconds=0` desactiva la expiración para esa tarea. La tarea permanece indefinidamente a menos que la borres manualmente desde el dashboard.

### Activar limpieza periódica

El servidor debe ejecutarse con `--cleanup-interval` para expirar tareas automáticamente:

```bash
python -m lapinq server --worker --port 8001 --cleanup-interval 60
```

Esto revisa tareas expiradas cada 60 segundos. Sin esta bandera, el TTL se almacena pero nunca se aplica.

## Cliente Asíncrono

```python
from lapinq import AsyncTaskQueue

async def main():
    tasks = AsyncTaskQueue(server_url="http://localhost:8001")

    @tasks.task(name="saludo")
    async def saludar(nombre: str):
        return f"¡Hola, {nombre}!"

    ref = await saludar.aqueue(nombre="Mundo")
    result = await ref.awaitait(timeout=30)
    print(result["status"])

    await tasks.close()
```
