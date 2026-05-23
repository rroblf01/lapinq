"""
Django + Lapinq Example
========================
Run with: python -m lapinq server --worker

Then in another terminal:
    DJANGO_SETTINGS_MODULE=examples.django_app.settings python -c "
        import django; django.setup()
        from examples.django_app.tasks import add, hello
        # Enqueue tasks
        ...
    "
"""

from __future__ import annotations

import os

from lapinq.client import TaskQueue

SERVER_URL = os.environ.get("LAPINQ_SERVER_URL", "http://127.0.0.1:8001")
task_queue = TaskQueue(server_url=SERVER_URL, queue_name="django")


@task_queue.task(name="add", max_retries=0)
def add(a: int, b: int) -> int:
    return a + b


@task_queue.task(name="hello", max_retries=0)
def hello(name: str, greeting: str = "Hello") -> str:
    return f"{greeting}, {name}!"


__all__ = ["add", "hello", "task_queue"]
