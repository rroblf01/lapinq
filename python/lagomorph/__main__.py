from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="lagomorph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    server_parser = subparsers.add_parser("server", help="Start the lagomorph server")
    server_parser.add_argument("--host", default="0.0.0.0")
    server_parser.add_argument("--port", type=int, default=8001)
    server_parser.add_argument("--database-url", default=None)
    server_parser.add_argument("--concurrency", type=int, default=4)

    execute_parser = subparsers.add_parser("execute", help="Execute a task (internal)")
    execute_parser.add_argument("task_id", help="Task ID to execute")

    worker_parser = subparsers.add_parser("worker", help="Start Python native worker")
    worker_parser.add_argument("--database-url", default=None)
    worker_parser.add_argument("--concurrency", type=int, default=4)
    worker_parser.add_argument("--poll-interval", type=float, default=0.1)
    worker_parser.add_argument("--task-timeout", type=int, default=300)

    args = parser.parse_args()

    if args.command == "server":
        _run_server(args)
    elif args.command == "execute":
        _run_execute(args)
    elif args.command == "worker":
        _run_worker(args)


def _run_server(args: argparse.Namespace) -> None:
    from lagomorph.server import create_app

    database_url = args.database_url or os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/lagomorph"
    )
    app = create_app(database_url=database_url)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def _run_execute(args: argparse.Namespace) -> None:
    from lagomorph.execute import execute_task

    import asyncio

    asyncio.run(execute_task(args.task_id))


def _run_worker(args: argparse.Namespace) -> None:
    from lagomorph.worker import run_worker

    database_url = args.database_url or os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/lagomorph"
    )
    import asyncio

    asyncio.run(
        run_worker(
            database_url=database_url,
            concurrency=args.concurrency,
            poll_interval=args.poll_interval,
            task_timeout=args.task_timeout,
        )
    )


if __name__ == "__main__":
    main()
