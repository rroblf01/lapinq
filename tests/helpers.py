from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


async def poll_until(
    condition: Callable[[], Any],
    timeout: float = 10,
    interval: float = 0.05,
) -> Any:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        result = condition()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return result
        await asyncio.sleep(interval)
    return None
