from __future__ import annotations

import asyncio
import logging
import os

import httpx
from fastapi import FastAPI
from lapinq.client import AsyncTaskQueue

logger = logging.getLogger("lapinq.example")

app = FastAPI(title="Lagomorph Example")

server_url = os.environ.get("LAGOMORPH_SERVER_URL", "http://lapinq-server:8001")
queue = AsyncTaskQueue(server_url=server_url, queue_name="example")
api_client = httpx.AsyncClient(base_url=server_url)


@queue.task
async def send_email(recipient: str, subject: str, body: str) -> str:
    logger.info("Sending email to %s: %s", recipient, subject)
    await asyncio.sleep(5)  # Simulate email sending delay
    logger.info("Email sent to %s", recipient)
    return f"sent to {recipient}: {subject}"


@app.on_event("shutdown")
async def shutdown() -> None:
    await queue.close()
    await api_client.aclose()


@app.post("/send-email")
async def send_email_endpoint(recipient: str, subject: str, body: str) -> dict:
    resp = await send_email.aqueue(recipient, subject, body)
    return {"task_id": resp.json()["task_id"]}


@app.get("/status/{task_id}")
async def status(task_id: str) -> dict:
    r = await api_client.get(f"/api/tasks/{task_id}")
    if r.status_code == 404:
        return {"status": "not found"}
    return r.json()
