# Changelog

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
- mkdocs.yml repo URL corrected to `ricardorobles/lapinq`
- `inspect.getmodule()` now raises clear error when module is unresolvable
