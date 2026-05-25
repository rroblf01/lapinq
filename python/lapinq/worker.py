from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
import uuid
from typing import Any

from lapinq.storage import Storage

logger = logging.getLogger("lapinq.worker")

HEARTBEAT_INTERVAL = float(os.environ.get("LAPINQ_HEARTBEAT_INTERVAL", "15.0"))
MAX_IDLE_BACKOFF = float(os.environ.get("LAPINQ_MAX_IDLE_BACKOFF", "5.0"))
STALE_RECOVERY_INTERVAL = float(os.environ.get("LAPINQ_STALE_RECOVERY_INTERVAL", "300"))


async def _worker_loop(
    storage: Storage,
    worker_id: str,
    concurrency: int,
    poll_interval: float,
    task_timeout: float,
    execute_fn: Any,
) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    shutdown_event = asyncio.Event()
    active_tasks: set[asyncio.Task[None]] = set()
    idle_backoff = poll_interval

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: _handle_signal(s, shutdown_event, worker_id),
            )
    except (ValueError, RuntimeError):
        pass

    heartbeat_task = asyncio.create_task(_heartbeat_loop(storage, worker_id, shutdown_event))
    stale_task = asyncio.create_task(
        _stale_recovery_loop(storage, int(STALE_RECOVERY_INTERVAL), shutdown_event)
    )

    async def process_task(task_data: dict) -> None:
        try:
            task_id = task_data["id"]
            webhook_url = task_data.get("webhook_url")
            try:
                result = await asyncio.wait_for(
                    execute_fn(task_data),
                    timeout=task_timeout,
                )
                logger.info("Task %s completed: %s", task_id, result)
                if result is not None:
                    await storage.complete_task(task_id, result=json.dumps(result))
                else:
                    await storage.complete_task(task_id)
                if webhook_url:
                    from lapinq.execute import _fire_webhook
                    asyncio.ensure_future(
                        _fire_webhook(webhook_url, task_id, "completed", result=json.dumps(result) if result is not None else None)
                    )
            except TimeoutError:
                logger.warning("Task %s timed out after %ds", task_id, task_timeout)
                await storage.fail_task(task_id, error="timed out")
                if webhook_url:
                    from lapinq.execute import _fire_webhook
                    asyncio.ensure_future(
                        _fire_webhook(webhook_url, task_id, "failed", error="timed out")
                    )
            except Exception as e:
                logger.exception("Task %s failed: %s", task_id, e)
                with contextlib.suppress(Exception):
                    await storage.fail_task(task_id, error=str(e))
                if webhook_url:
                    from lapinq.execute import _fire_webhook
                    asyncio.ensure_future(
                        _fire_webhook(webhook_url, task_id, "failed", error=str(e))
                    )
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
                idle_backoff = poll_interval
                t = asyncio.create_task(process_task(task_data))
                active_tasks.add(t)
                t.add_done_callback(active_tasks.discard)
            else:
                semaphore.release()
                await asyncio.sleep(idle_backoff)
                idle_backoff = min(idle_backoff * 2, MAX_IDLE_BACKOFF)
    except asyncio.CancelledError:
        pass
    finally:
        heartbeat_task.cancel()
        stale_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        with contextlib.suppress(asyncio.CancelledError):
            await stale_task
        logger.info("Worker %s shutting down, waiting for %d active tasks...", worker_id, len(active_tasks))
        if active_tasks:
            await asyncio.wait(active_tasks, timeout=30)
        await storage.close()
        logger.info("Worker %s stopped", worker_id)


async def run_worker(
    database_url: str | None = None,
    concurrency: int = 4,
    poll_interval: float = 0.1,
    task_timeout: float = 300,
) -> None:
    database_url = database_url or os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lapinq")
    worker_id = str(uuid.uuid4())
    storage = await Storage.create(database_url, max_size=concurrency + 2)

    async def subprocess_execute(task_data: dict) -> str | None:
        task_id = task_data["id"]
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "lapinq",
            "execute",
            str(task_id),
            env={**os.environ, "DATABASE_URL": database_url, "LAPINQ_WORKER_ID": worker_id},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=task_timeout)
        except TimeoutError:
            proc.kill()
            raise
        if proc.returncode == 0:
            result = stdout.decode().strip()
            return result
        else:
            error = stderr.decode().strip()
            raise RuntimeError(error)

    await _worker_loop(
        storage, worker_id, concurrency, poll_interval, task_timeout, subprocess_execute,
    )


async def run_worker_inline(
    storage: Storage,
    concurrency: int = 4,
    poll_interval: float = 0.1,
    task_timeout: float = 300,
) -> None:
    from lapinq.execute import execute_task_inline

    worker_id = str(uuid.uuid4())
    await _worker_loop(
        storage, worker_id, concurrency, poll_interval, task_timeout, execute_task_inline,
    )


async def _heartbeat_loop(storage: Storage, worker_id: str, shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        try:
            await storage.heartbeat(worker_id)
        except Exception:
            logger.exception("Heartbeat failed for worker %s", worker_id)
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def _stale_recovery_loop(storage: Storage, max_running_seconds: int, shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        try:
            recovered = await storage.recover_stale_tasks(max_running_seconds=max_running_seconds)
            if recovered:
                logger.info("Recovered %d stale tasks", len(recovered))
        except Exception:
            logger.exception("Stale recovery failed")
        await asyncio.sleep(max_running_seconds)


def _handle_signal(sig: signal.Signals, shutdown_event: asyncio.Event, worker_id: str) -> None:
    logger.info("Worker %s received signal %s", worker_id, sig.name)
    shutdown_event.set()
