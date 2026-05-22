from __future__ import annotations

import asyncio
import os
import sys
import uuid

from lagomorph.storage import Storage


async def run_worker(
    database_url: str | None = None,
    concurrency: int = 4,
    poll_interval: float = 0.1,
    task_timeout: int = 300,
) -> None:
    database_url = database_url or os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/lagomorph"
    )
    worker_id = str(uuid.uuid4())
    storage = await Storage.create(database_url, max_size=concurrency + 2)

    semaphore = asyncio.Semaphore(concurrency)
    running = True

    async def process_task(task_data: dict) -> None:
        async with semaphore:
            task_id = task_data["id"]
            try:
                async with asyncio.timeout(task_timeout):
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable,
                        "-m",
                        "lagomorph",
                        "execute",
                        str(task_id),
                        env={**os.environ, "LAGOMORPH_WORKER_ID": worker_id},
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode == 0:
                        print(
                            f"Task {task_id} completed: {stdout.decode().strip()}"
                        )
                    else:
                        print(
                            f"Task {task_id} failed: {stderr.decode().strip()}",
                            file=sys.stderr,
                        )
            except TimeoutError:
                print(f"Task {task_id} timed out", file=sys.stderr)

            # Task was already deleted by execute.py, but just in case
            try:
                await storage.complete_task(task_id)
            except Exception:
                pass

    print(
        f"Worker {worker_id} starting (concurrency={concurrency}, "
        f"poll_interval={poll_interval}s, timeout={task_timeout}s)"
    )

    try:
        while running:
            task_data = await storage.claim_task(worker_id)
            if task_data is not None:
                asyncio.create_task(process_task(task_data))
            else:
                await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        pass
    finally:
        await storage.close()
