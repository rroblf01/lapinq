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

## Tu Primera Tarea

```python
from lapinq import TaskQueue

tasks = TaskQueue(server_url="http://localhost:8001")

@tasks.task(name="saludo")
def saludar(nombre: str):
    return f"¡Hola, {nombre}!"

# Encola — se ejecuta asíncronamente en el worker
respuesta = saludar.queue(nombre="Mundo")
print(respuesta.json())  # {"task_id": "..."}
```

## Cliente Asíncrono

```python
from lapinq import AsyncTaskQueue

async def main():
    tasks = AsyncTaskQueue(server_url="http://localhost:8001")

    @tasks.task(name="saludo")
    async def saludar(nombre: str):
        return f"¡Hola, {nombre}!"

    respuesta = await saludar.aqueue(nombre="Mundo")
    print(respuesta.json())

    await tasks.close()
```
