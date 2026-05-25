# Client API Reference

## `TaskQueue`

Synchronous client for defining and enqueuing tasks.

### `__init__(server_url, queue_name, timeout, api_key, default_ttl_seconds)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server_url` | `str` | `"http://127.0.0.1:8001"` | URL of the lapinq server |
| `queue_name` | `str` | `"default"` | Default queue name |
| `timeout` | `float` | `30.0` | HTTP request timeout in seconds |
| `api_key` | `str \| None` | `None` | API key for `X-API-Key` header |
| `default_ttl_seconds` | `float \| None` | `None` | Default TTL applied to tasks without explicit `ttl_seconds` |

### `task(name=None, queue_name=None, scheduled_at=None, max_retries=None, priority=0, ttl_seconds=None, metadata=None, retry_delay=None, retry_backoff=None, webhook_url=None)`

Decorator that registers a function as a task. Can be used with or without parentheses.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str \| None` | Function name | Explicit task name |
| `queue_name` | `str \| None` | From `__init__` | Queue to enqueue in |
| `scheduled_at` | `str \| None` | `None` | ISO 8601 datetime for delayed execution |
| `max_retries` | `int \| None` | `3` | Max retry attempts on failure |
| `priority` | `int` | `0` | Higher = runs first |
| `ttl_seconds` | `int \| None` | `None` | Auto-delete task after N seconds; `0` = do not persist |
| `metadata` | `dict \| None` | `None` | Arbitrary key-value pairs stored as JSONB |
| `retry_delay` | `float \| None` | `None` | Fixed delay between retries (seconds) |
| `retry_backoff` | `bool \| None` | `None` | Exponential backoff (default `true`) |
| `webhook_url` | `str \| None` | `None` | URL called via POST on completion/failure |

The decorated function:
- Remains callable as the original function
- Gets a `.queue()` method that returns a `TaskRef` object
- Gets a `.task_name` attribute

### `batch_enqueue(tasks)`

Enqueue multiple tasks in a single request.

| Parameter | Type | Description |
|-----------|------|-------------|
| `tasks` | `list[dict]` | List of task payloads |

Returns `httpx.Response`.

### `close()`

Close the underlying HTTP client connection.

## `AsyncTaskQueue`

Asynchronous client. Same interface as `TaskQueue` but uses `httpx.AsyncClient`.

### `__init__(server_url, queue_name, timeout, api_key, default_ttl_seconds)`

Same parameters as `TaskQueue`.

### `task(name=None, queue_name=None, scheduled_at=None, max_retries=None, priority=0, ttl_seconds=None, metadata=None, retry_delay=None, retry_backoff=None, webhook_url=None)`

Same parameters as `TaskQueue`. Adds a `.aqueue()` coroutine that returns a `TaskRef` object.

### `async batch_enqueue(tasks)`

Async version of `batch_enqueue`. Returns `httpx.Response`.

### `async close()`

Close the underlying async HTTP client connection.

## `TaskRef`

Returned by `.queue()` and `.aqueue()`. Wraps the HTTP response from the server.

| Attribute / Method | Description |
|--------------------|-------------|
| `.task_id` | Task UUID string (or `None` for TTL-zero tasks) |
| `.json()` | Response body as dict |
| `.status_code` | HTTP status code |
| `.wait(timeout=30)` | Poll until task completes or timeout is reached (sync) |
| `await .awaitait(timeout=30)` | Poll until task completes or timeout is reached (async) |

## Examples

```python
from lapinq import TaskQueue, AsyncTaskQueue

# Sync client
tasks = TaskQueue(server_url="http://localhost:8001")

@tasks.task(name="sync_task")
def sync_task(x: int):
    return x * 2

ref = sync_task.queue(x=42)
print(ref.task_id)           # "uuid-here"
print(ref.wait(timeout=30))  # {"status": "completed", "result": "84", ...}

# Async client
async_tasks = AsyncTaskQueue(server_url="http://localhost:8001")

@async_tasks.task(name="async_task")
async def async_task(x: int):
    return x * 2

ref = await async_task.aqueue(x=42)
print(ref.task_id)                              # "uuid-here"
result = await ref.awaitait(timeout=30)
print(result["status"])                         # "completed"
await async_tasks.close()
```
