from __future__ import annotations

import pytest

DATABASE_URL = "postgresql://postgres:test@localhost:5432/lagomorph_test"


@pytest.fixture(autouse=True)
async def cleanup_db():
    import asyncpg

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM lagomorph_tasks")
    finally:
        await conn.close()
    yield
