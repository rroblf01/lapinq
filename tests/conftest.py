from __future__ import annotations

import asyncio
import os
import sys

import pytest
from lagomorph.storage import SQL_SCHEMA

DATABASE_URL: str | None = os.environ.get("DATABASE_URL")


@pytest.fixture(scope="session", autouse=True)
def _postgres_container():
    global DATABASE_URL

    if DATABASE_URL is not None:
        async def init_schema() -> None:
            import asyncpg

            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute(SQL_SCHEMA)
            finally:
                await conn.close()

        asyncio.run(init_schema())
        yield
        return

    from testcontainers.postgres import PostgresContainer

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
