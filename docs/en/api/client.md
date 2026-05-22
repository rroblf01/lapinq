# Client API Reference

## `TaskQueue`

Synchronous client for defining and enqueuing tasks.

### `__init__(server_url, queue_name, timeout)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server_url` | `str` | `"http://127.0.0.1:8001"` | URL of the lapinq server |
| `queue_name` | `str` | `"default"` | Default queue name |
| `timeout` | `float` | `30.0` | HTTP request timeout in seconds |

### `task(name=None, queue_name=None, scheduled_at=None, max_retries=None, priority=0, ttl_seconds=None)`

Decorator that registers a function as a task. Can be used with or without parentheses.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str \| None` | Function name | Explicit task name |
| `queue_name` | `str \| None` | From `__init__` | Queue to enqueue in |
| `scheduled_at` | `str \| None` | `None` | ISO 8601 datetime for delayed execution |
| `max_retries` | `int \| None` | `3` | Max retry attempts on failure |
| `priority` | `int` | `0` | Higher = runs first |
| `ttl_seconds` | `int \| None` | `None` | Auto-delete task after N seconds; `0` = do not persist |

The decorated function:
- Remains callable as the original function
- Gets a `.queue()` method to enqueue the task
- Gets a `.task_name` attribute

### `close()`

Close the underlying HTTP client connection.

## `AsyncTaskQueue`

Asynchronous client. Same interface as `TaskQueue` but uses `httpx.AsyncClient`.

### `__init__(server_url, queue_name, timeout)`

Same parameters as `TaskQueue`.

### `task(name=None, queue_name=None, scheduled_at=None, max_retries=None, priority=0, ttl_seconds=None)`

Same parameters as `TaskQueue`. Adds a `.aqueue()` coroutine to the decorated function.

### `async close()`

Close the underlying async HTTP client connection.

## Examples

```python
from lapinq import TaskQueue, AsyncTaskQueue

# Sync client
tasks = TaskQueue(server_url="http://localhost:8001")

@tasks.task(name="sync_task")
def sync_task(x: int):
    return x * 2

response = sync_task.queue(x=42)
task_id = response.json()["task_id"]

# Async client
async_tasks = AsyncTaskQueue(server_url="http://localhost:8001")

@async_tasks.task(name="async_task")
async def async_task(x: int):
    return x * 2

response = await async_task.aqueue(x=42)
task_id = response.json()["task_id"]
await async_tasks.close()
```
