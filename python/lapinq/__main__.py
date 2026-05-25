from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid

from lapinq.log import configure_logging

configure_logging()


def main() -> None:
    parser = argparse.ArgumentParser(prog="lapinq")
    subparsers = parser.add_subparsers(dest="command", required=True)

    server_parser = subparsers.add_parser("server", help="Start the lapinq server")
    server_parser.add_argument("--host", default="0.0.0.0")
    server_parser.add_argument("--port", type=int, default=8001)
    server_parser.add_argument("--database-url", default=None)
    server_parser.add_argument("--concurrency", type=int, default=4)
    server_parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    server_parser.add_argument("--worker", action="store_true")
    server_parser.add_argument("--worker-concurrency", type=int, default=4)
    server_parser.add_argument("--worker-poll-interval", type=float, default=0.1)
    server_parser.add_argument("--worker-timeout", type=int, default=300)
    server_parser.add_argument("--cleanup-interval", type=float, default=0)
    server_parser.add_argument("--scheduler", action="store_true", help="Enable periodic/cron task scheduler")
    server_parser.add_argument("--scheduler-interval", type=float, default=60.0, help="Scheduler check interval in seconds")

    execute_parser = subparsers.add_parser("execute", help="Execute a task (internal)")
    execute_parser.add_argument("task_id", help="Task ID to execute")

    worker_parser = subparsers.add_parser("worker", help="Start Python native worker")
    worker_parser.add_argument("--database-url", default=None)
    worker_parser.add_argument("--concurrency", type=int, default=4)
    worker_parser.add_argument("--poll-interval", type=float, default=0.1)
    worker_parser.add_argument("--task-timeout", type=int, default=300)

    task_parser = subparsers.add_parser("task", help="Manage tasks")
    task_sub = task_parser.add_subparsers(dest="task_command", required=True)
    _add_task_list_parser(task_sub)
    _add_task_get_parser(task_sub)
    _add_task_cancel_parser(task_sub)
    _add_task_requeue_parser(task_sub)

    args = parser.parse_args()

    if args.command == "server":
        _run_server(args)
    elif args.command == "execute":
        _run_execute(args)
    elif args.command == "worker":
        _run_worker(args)
    elif args.command == "task":
        asyncio.run(_run_task(args))


def _add_task_list_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("list", help="List tasks")
    p.add_argument("--queue", "-q", default=None, help="Filter by queue name")
    p.add_argument("--status", "-s", default=None, choices=["pending", "running", "completed", "failed", "cancelled", "expired"], help="Filter by status")
    p.add_argument("--limit", "-l", type=int, default=20, help="Max results")
    p.add_argument("--database-url", default=None, help="PostgreSQL connection URL")
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON")


def _add_task_get_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("get", help="Get a task by ID")
    p.add_argument("task_id", help="Task UUID")
    p.add_argument("--database-url", default=None)
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON")


def _add_task_cancel_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("cancel", help="Cancel a pending task")
    p.add_argument("task_id", help="Task UUID")
    p.add_argument("--database-url", default=None)


def _add_task_requeue_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("requeue", help="Requeue a failed task")
    p.add_argument("task_id", help="Task UUID")
    p.add_argument("--database-url", default=None)


def _run_server(args: argparse.Namespace) -> None:
    logging.getLogger().setLevel(args.log_level.upper())
    from lapinq.server import create_app

    database_url = args.database_url or os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lapinq")
    api_key = os.environ.get("LAPINQ_API_KEY")
    rate_limit_str = os.environ.get("LAPINQ_RATE_LIMIT", "0")
    rate_limit = int(rate_limit_str) if rate_limit_str.isdigit() else 0
    app = create_app(
        database_url=database_url,
        api_key=api_key,
        rate_limit=rate_limit,
        worker=args.worker,
        worker_concurrency=args.worker_concurrency,
        worker_poll_interval=args.worker_poll_interval,
        worker_timeout=args.worker_timeout,
        cleanup_interval=args.cleanup_interval,
        scheduler=args.scheduler,
        scheduler_interval=args.scheduler_interval,
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


def _run_execute(args: argparse.Namespace) -> None:
    from lapinq.execute import execute_task

    asyncio.run(execute_task(args.task_id))


def _run_worker(args: argparse.Namespace) -> None:
    logging.getLogger().setLevel(logging.INFO)
    from lapinq.worker import run_worker

    database_url = args.database_url or os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lapinq")
    asyncio.run(
        run_worker(
            database_url=database_url,
            concurrency=args.concurrency,
            poll_interval=args.poll_interval,
            task_timeout=args.task_timeout,
        )
    )


async def _run_task(args: argparse.Namespace) -> None:
    from lapinq.storage import Storage

    database_url = args.database_url or os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lapinq")
    storage = await Storage.create(database_url)
    try:
        if args.task_command == "list":
            tasks = await storage.list_tasks(
                queue_name=args.queue,
                status=args.status,
                limit=args.limit,
            )
            if getattr(args, "json", False):
                print(json.dumps([_serialize_task_cli(t) for t in tasks], indent=2, default=str))
            else:
                if not tasks:
                    print("No tasks found.")
                    return
                for t in tasks:
                    tid = str(t["id"])[:8]
                    status = t["status"]
                    name = t["task_name"]
                    queue = t["queue_name"]
                    created = t["created_at"].strftime("%H:%M:%S") if t.get("created_at") else ""
                    print(f"  {tid}  {status:12s}  {name:20s}  queue={queue}  {created}")

        elif args.task_command == "get":
            task = await storage.get_task(uuid.UUID(args.task_id))
            if task is None:
                print(f"Task {args.task_id} not found.", file=sys.stderr)
                sys.exit(1)
            if getattr(args, "json", False):
                print(json.dumps(_serialize_task_cli(task), indent=2, default=str))
            else:
                _print_task(task)

        elif args.task_command == "cancel":
            ok = await storage.cancel_task(uuid.UUID(args.task_id))
            if ok:
                print(f"Cancelled task {args.task_id}")
            else:
                print(f"Task {args.task_id} not found or not pending.", file=sys.stderr)
                sys.exit(1)

        elif args.task_command == "requeue":
            ok = await storage.requeue_task(uuid.UUID(args.task_id))
            if ok:
                print(f"Requeued task {args.task_id}")
            else:
                print(f"Task {args.task_id} not found or not failed.", file=sys.stderr)
                sys.exit(1)
    finally:
        await storage.close()


def _serialize_task_cli(task: dict) -> dict:
    result = dict(task)
    for key in ("id",):
        if key in result and isinstance(result[key], uuid.UUID):
            result[key] = str(result[key])
    for key in ("created_at", "started_at", "completed_at", "scheduled_at", "last_heartbeat"):
        if key in result and result[key] is not None:
            result[key] = result[key].isoformat()
    return result


def _print_task(task: dict) -> None:
    print(f"  ID:         {task['id']}")
    print(f"  Name:       {task['task_name']}")
    print(f"  Queue:      {task['queue_name']}")
    print(f"  Status:     {task['status']}")
    print(f"  Module:     {task['module_path']}")
    print(f"  Args:       {task.get('args', [])}")
    print(f"  Kwargs:     {task.get('kwargs', {})}")
    print(f"  Attempts:   {task.get('attempts', 0)}")
    print(f"  Max retry:  {task.get('max_retries', 3)}")
    print(f"  Priority:   {task.get('priority', 0)}")
    if task.get("error"):
        print(f"  Error:      {task['error']}")
    if task.get("result"):
        print(f"  Result:     {task['result']}")
    if task.get("progress") is not None:
        print(f"  Progress:   {task['progress']}% {task.get('progress_message', '')}")
    if task.get("metadata") and task["metadata"] != {}:
        print(f"  Metadata:   {task['metadata']}")
    if task.get("created_at"):
        print(f"  Created:    {task['created_at']}")
    if task.get("completed_at"):
        print(f"  Completed:  {task['completed_at']}")


if __name__ == "__main__":
    main()
