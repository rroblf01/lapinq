"""
FastAPI + Lapinq Example
========================
Run with: uvicorn examples.fastapi_app:app --reload
Or via lapinq: python -m lapinq server --worker
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from fastapi import FastAPI, HTTPException
from lapinq.client import AsyncTaskQueue

# --- Tasks ---

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("fastapi_example")

SERVER_URL = os.environ.get("LAPINQ_SERVER_URL", "http://127.0.0.1:8001")
task_queue = AsyncTaskQueue(server_url=SERVER_URL, queue_name="fastapi")


@task_queue.task(name="add", max_retries=0)
def add(a: int, b: int) -> int:
    return a + b


@task_queue.task(name="slow_square", max_retries=0)
def slow_square(n: int) -> int:
    time.sleep(2)
    return n * n


@task_queue.task(name="echo_message", max_retries=0)
async def echo_message(msg: str) -> str:
    await asyncio.sleep(0.1)
    return f"echo: {msg}"


# --- FastAPI app ---

app = FastAPI(title="Lapinq + FastAPI Demo")


@app.get("/")
async def root():
    return {
        "message": "Lapinq + FastAPI Demo",
        "endpoints": {
            "POST /square/{n}": "Enqueue a slow square calculation",
            "POST /echo": "Enqueue an async echo task",
            "GET /task/{task_id}": "Check task status and result",
        },
    }


@app.post("/square/{n}")
async def enqueue_square(n: int):
    resp = await slow_square.aqueue(n)
    if resp.status_code != 201:
        raise HTTPException(status_code=resp.status_code, detail=resp.json())
    return resp.json()


@app.post("/echo")
async def enqueue_echo(msg: str = "hello"):
    resp = await echo_message.aqueue(msg)
    if resp.status_code != 201:
        raise HTTPException(status_code=resp.status_code, detail=resp.json())
    return resp.json()


@app.get("/task/{task_id}")
async def get_task(task_id: str):
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{SERVER_URL}/api/v1/tasks/{task_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()
