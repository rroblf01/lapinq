from __future__ import annotations

import asyncio
import sys

import pytest
from testcontainers.postgres import PostgresContainer

DATABASE_URL: str | None = None

SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS lagomorph_tasks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_name  TEXT NOT NULL,
    task_name   TEXT NOT NULL,
    module_path TEXT NOT NULL,
    args        JSONB NOT NULL DEFAULT '[]',
    kwargs      JSONB NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','completed','failed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    worker_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON lagomorph_tasks(status, created_at);
"""


@pytest.fixture(scope="session", autouse=True)
def _postgres_container():
    global DATABASE_URL
    with PostgresContainer("postgres:16-alpine") as pg:
        DATABASE_URL = (
            f"postgresql://{pg.username}:{pg.password}"
            f"@{pg.get_container_host_ip()}:{pg.get_exposed_port(5432)}/{pg.dbname}"
        )

        async def init_schema() -> None:
            import asyncpg

            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute(SQL_SCHEMA)
            finally:
                await conn.close()

        asyncio.run(init_schema())

        for mod_name, mod in list(sys.modules.items()):
            if hasattr(mod, "DATABASE_URL") and (mod_name.startswith("test_") or mod_name.startswith("tests.")):
                mod.DATABASE_URL = DATABASE_URL  # ty: ignore
        yield


@pytest.fixture(autouse=True)
async def cleanup_db(request):
    if "test_client" in request.module.__name__:
        yield
        return
    import asyncpg

    assert DATABASE_URL is not None
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM lagomorph_tasks")
    finally:
        await conn.close()
    yield
