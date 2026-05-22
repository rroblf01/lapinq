from __future__ import annotations

import argparse
import logging
import os

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
    logging.getLogger().setLevel(args.log_level.upper())
    from lapinq.server import create_app

    database_url = args.database_url or os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lapinq")
    api_key = os.environ.get("LAGOMORPH_API_KEY")
    rate_limit_str = os.environ.get("LAGOMORPH_RATE_LIMIT", "0")
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
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


def _run_execute(args: argparse.Namespace) -> None:
    import asyncio

    from lapinq.execute import execute_task

    asyncio.run(execute_task(args.task_id))


def _run_worker(args: argparse.Namespace) -> None:
    logging.getLogger().setLevel(logging.INFO)
    from lapinq.worker import run_worker

    database_url = args.database_url or os.environ.get("DATABASE_URL", "postgresql://localhost:5432/lapinq")
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
