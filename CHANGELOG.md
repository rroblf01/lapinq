# Changelog

## [1.3.0] - 2026-05-26

### Added
- Authentication system — login/logout, session tokens (HMAC-signed cookies), role-based dashboard access
- Admin user management page — create/delete users, change roles, configure per-queue permissions
- Change password endpoint for authenticated users
- WebSocket authentication — first-message protocol with `__auth__` token before data exchange
- Dashboard login page with error feedback
- Task name filter in dashboard — filter tasks by name via WebSocket
- Session token embedded directly in HTML (avoids httponly cookie restrictions for WebSocket auth)
- `/admin/users` — paginated user table with role/permission editing
- `/account/password` — password change endpoint (current password required)

### Fixed
- WebSocket `_send` crash on DB pool closure during shutdown — `shutting_down` flag checked before any query, raises `WebSocketDisconnect(1001)` cleanly with no error traceback
- WebSocket infinite reconnect loop — client no longer reconnects on close codes 4001 (auth failure), 1011 (server error), or 1001 (going away); exponential backoff added for other reconnections
- WebSocket `recv_task.result()` `RuntimeError` when socket already closed — wrapped in try/except, converts to clean `WebSocketDisconnect`
- Queue filter dropdown now updates dynamically when new queues appear — server sends `queues` list in WS payload, client rebuilds `<select>` options preserving current selection
- Missing `queues_html`/`tasks_html` imports in server.py (NameError at runtime)
- Dead `_get_session_token()` function referencing browser `document` from Python code
- Unused `queue_options` variable in dashboard.py
- `base64.binascii.Error` → broader `Exception` in password verification
- Type error in login handler (Starlette `FormData.get()` returns `UploadFile | str`, cast to `str`)
- E501 line-too-long in CSS, SQL, and JS template strings

### Changed
- Dashboard filters now include Task Name field
- WebSocket clients must authenticate via `{type:"auth",token:"..."}` on connect
- Session cookie is `httponly` with `samesite=lax`, 24h expiry
- Requires `LAPINQ_SESSION_SECRET` environment variable (auto-generated if empty)
- Default admin user (`admin`/`admin`) created on first startup via `ensure_default_admin()`
- `/sw.js` returns 204 No Content (silences browser service worker 404 in logs)

## [1.2.0] - 2026-05-25

### Added
- Task metadata — arbitrary JSONB key-value pairs per task, visible in dashboard
- Task progress tracking — worker can update progress (0–100%) and message via `PATCH /api/v1/tasks/{id}/progress`
- Batch enqueue — `POST /api/v1/enqueue/batch` for bulk task creation (up to 1000 tasks)
- Configurable retry policies — `retry_delay` (fixed delay) and `retry_backoff` (exponential, default) per task
- Default TTL — `default_ttl_seconds` on `TaskQueue`/`AsyncTaskQueue` applied when no explicit `ttl_seconds`
- Webhook callbacks — `webhook_url` per task; worker fires POST on completion/failure
- `TaskRef` client wrapper — `.task_id`, `.wait(timeout)`, `.awaitait(timeout)` for result polling
- Manual retry — raise `lapinq.RetryError(countdown=N)` inside a task function to retry with custom delay
- CLI task management — `lapinq task list|get|cancel|requeue` with `--json` output
- Cron-based periodic scheduler — `lapinq server --scheduler` with 5-field cron expressions
- New `lapinq_scheduled_tasks` table for defining recurring task schedules

### Changed
- `.queue()` and `.aqueue()` now return a `TaskRef` object (backward-compatible with `.json()` and `.status_code`)

## [1.0.0] - 2026-05-23

### Added
- PostgreSQL-backed task queue with Rust + Python workers
- REST API with Starlette server
- WebSocket dashboard with real-time updates
- Prometheus metrics endpoint
- Task scheduling (`scheduled_at`)
- TTL support with auto-cleanup
- Retry with exponential backoff
- Priority-based task ordering
- Task cancellation (soft-delete) and requeue
- API key authentication (constant-time comparison)
- Rate limiting (asyncio.Lock protected)
- Request ID middleware for tracing
- Content-Length check before JSON parse
- Versioned API prefix (`/api/v1/`)
- Schema migrations with version tracking
- Archive/retention policy for old tasks
- Graceful shutdown with signal handlers
- Dashboard actions (cancel/requeue with confirmation)
- Dashboard pagination ("Show more")
- WebSocket wss:// support for HTTPS
- Dashboard shows cancelled status
- Rust worker: stale task recovery, heartbeat shutdown coordination
- Rust worker: configurable TLS support
- Python worker: deduplicated loop, exponential idle backoff
- Client library: async context manager, API key support
- CLI entry point via `[project.scripts]`
- `abi3` wheels for broader Python compatibility
- `.env.example` for local development
- CHANGELOG.md
- Development Status updated to Beta

### Changed
- `cancel_task` now soft-deletes (sets `status = 'cancelled'`) instead of hard DELETE
- `cleanup_expired_tasks` now sets `status = 'expired'` instead of hard DELETE
- Packed schema version `INT` → `DOUBLE PRECISION` in Rust for consistency with Python
- API routes moved from `/api/` to `/api/v1/`
- Env vars renamed from `LAGOMORPH_*` to `LAPINQ_*`
- `LAGOMORPH_PYTHON` → `LAPINQ_PYTHON` (with fallback)
- Dashboard title: "Lagomorph Dashboard" → "Lapinq Dashboard"
- Dockerfile binary: `lagomorph-worker` → `lapinq-worker`
- Dockerfile CMD: `lagomorph` → `lapinq`

### Fixed
- Bare `except: pass` in Rust executor now logs warnings
- `list_tasks` parameter validation returns 400 instead of 500
- Rate limiter uses `asyncio.Lock` to prevent race conditions
- API key comparison uses `hmac.compare_digest` (constant-time)
- `listen_for_changes` uses separate connection instead of pool
- WebSocket closes on send errors instead of silent loop
- Worker idle backoff now exponential (0.1s → max 5s)
- mkdocs.yml repo URL corrected to `rroblf01/lapinq`
- `inspect.getmodule()` now raises clear error when module is unresolvable
