# Client API Reference

## `TaskQueue`

The main client class for defining and enqueuing tasks.

### `__init__(server_url, queue_name, timeout)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server_url` | `str` | `"http://127.0.0.1:8001"` | URL of the lagomorph server |
| `queue_name` | `str` | `"default"` | Default queue name for tasks |
| `timeout` | `float` | `30.0` | HTTP request timeout in seconds |

### `task(name=None, queue_name=None)`

Decorator that registers a function as a task.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str \| None` | Function name | Explicit task name |
| `queue_name` | `str \| None` | Queue from `__init__` | Queue to enqueue in |

Returns a wrapper function that, when called, sends an HTTP POST to the server to enqueue the task.

### `close()`

Close the underlying HTTP client connection.
