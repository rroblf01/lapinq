from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
import uuid

from lapinq.storage import Storage

logger = logging.getLogger("lapinq.worker")

HEARTBEAT_INTERVAL = float(os.environ.get("LAPINQ_HEARTBEAT_INTERVAL", "15.0"))


async def run_worker(
    database_url: str | None = None,
    concurrency: int = 4,
    poll_interval: float = 0.1,
    task_timeout: int = 300,
) -> None:
    database_url = database_url or os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lapinq")
    worker_id = str(uuid.uuid4())
    storage = await Storage.create(database_url, max_size=concurrency + 2)

    semaphore = asyncio.Semaphore(concurrency)
    shutdown_event = asyncio.Event()
    active_tasks: set[asyncio.Task[None]] = set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: _handle_signal(s, shutdown_event, worker_id),
        )

    heartbeat_task = asyncio.create_task(_heartbeat_loop(storage, worker_id, shutdown_event))

    async def process_task(task_data: dict) -> None:
        try:
            task_id = task_data["id"]
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "lapinq",
                    "execute",
                    str(task_id),
                    env={**os.environ, "DATABASE_URL": database_url, "LAGOMORPH_WORKER_ID": worker_id},
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=task_timeout)
                if proc.returncode == 0:
                    result = stdout.decode().strip()
                    logger.info("Task %s completed: %s", task_id, result)
                    await storage.complete_task(task_id, result=result)
                else:
                    error = stderr.decode().strip()
                    logger.warning("Task %s failed: %s", task_id, error)
                    await storage.fail_task(task_id, error=error)
            except TimeoutError:
                logger.warning("Task %s timed out after %ds", task_id, task_timeout)
                await storage.fail_task(task_id, error="timed out")
            except Exception as e:
                logger.exception("Task %s failed: %s", task_id, e)
                with contextlib.suppress(Exception):
                    await storage.fail_task(task_id, error=str(e))
        finally:
            semaphore.release()

    logger.info(
        "Worker %s starting (concurrency=%d, poll_interval=%.1fs, timeout=%ds)",
        worker_id,
        concurrency,
        poll_interval,
        task_timeout,
    )

    try:
        while not shutdown_event.is_set():
            await semaphore.acquire()
            task_data = await storage.claim_task(worker_id)
            if task_data is not None:
                t = asyncio.create_task(process_task(task_data))
                active_tasks.add(t)
                t.add_done_callback(active_tasks.discard)
            else:
                semaphore.release()
                await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        pass
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        logger.info("Worker %s shutting down, waiting for %d active tasks...", worker_id, len(active_tasks))
        if active_tasks:
            await asyncio.wait(active_tasks, timeout=30)
        await storage.close()
        logger.info("Worker %s stopped", worker_id)


async def run_worker_inline(
    storage: Storage,
    concurrency: int = 4,
    poll_interval: float = 0.1,
    task_timeout: int = 300,
) -> None:
    from lapinq.execute import execute_task_inline

    worker_id = str(uuid.uuid4())
    semaphore = asyncio.Semaphore(concurrency)
    shutdown_event = asyncio.Event()
    active_tasks: set[asyncio.Task[None]] = set()

    heartbeat_task = asyncio.create_task(_heartbeat_loop(storage, worker_id, shutdown_event))

    async def process_task(task_data: dict) -> None:
        try:
            task_id = task_data["id"]
            try:
                result = await asyncio.wait_for(
                    execute_task_inline(task_data),
                    timeout=task_timeout,
                )
                logger.info("Task %s completed: %s", task_id, result)
                await storage.complete_task(task_id, result=json.dumps(result))
            except TimeoutError:
                logger.warning("Task %s timed out after %ds", task_id, task_timeout)
                await storage.fail_task(task_id, error="timed out")
            except Exception as e:
                logger.exception("Task %s failed: %s", task_id, e)
                with contextlib.suppress(Exception):
                    await storage.fail_task(task_id, error=str(e))
        finally:
            semaphore.release()

    logger.info(
        "Inline worker %s starting (concurrency=%d, poll_interval=%.1fs, timeout=%ds)",
        worker_id,
        concurrency,
        poll_interval,
        task_timeout,
    )

    try:
        while not shutdown_event.is_set():
            await semaphore.acquire()
            task_data = await storage.claim_task(worker_id)
            if task_data is not None:
                t = asyncio.create_task(process_task(task_data))
                active_tasks.add(t)
                t.add_done_callback(active_tasks.discard)
            else:
                semaphore.release()
                await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        pass
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        logger.info("Inline worker %s shutting down, waiting for %d active tasks...", worker_id, len(active_tasks))
        if active_tasks:
            await asyncio.wait(active_tasks, timeout=30)
        logger.info("Inline worker %s stopped", worker_id)


async def _heartbeat_loop(storage: Storage, worker_id: str, shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        try:
            await storage.heartbeat(worker_id)
        except Exception:
            logger.exception("Heartbeat failed for worker %s", worker_id)
        await asyncio.sleep(HEARTBEAT_INTERVAL)


def _handle_signal(sig: signal.Signals, shutdown_event: asyncio.Event, worker_id: str) -> None:
    logger.info("Worker %s received signal %s", worker_id, sig.name)
    shutdown_event.set()
