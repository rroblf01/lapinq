from __future__ import annotations

import sys
from unittest import mock

from lagomorph.__main__ import main


def test_cli_server_parses_defaults():
    with mock.patch.object(sys, "argv", ["lagomorph", "server"]), mock.patch(
        "lagomorph.__main__._run_server"
    ) as mock_run:
        main()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.host == "0.0.0.0"
        assert args.port == 8001
        assert args.concurrency == 4
        assert args.log_level == "info"


def test_cli_server_parses_custom():
    with mock.patch.object(
        sys, "argv",
        ["lagomorph", "server", "--host", "127.0.0.1", "--port", "9000", "--log-level", "debug"],
    ), mock.patch("lagomorph.__main__._run_server") as mock_run:
        main()
        args = mock_run.call_args[0][0]
        assert args.host == "127.0.0.1"
        assert args.port == 9000
        assert args.log_level == "debug"


def test_cli_execute_parses_task_id():
    with mock.patch.object(sys, "argv", ["lagomorph", "execute", "abc-123"]), mock.patch(
        "lagomorph.__main__._run_execute"
    ) as mock_run:
        main()
        args = mock_run.call_args[0][0]
        assert args.task_id == "abc-123"


def test_cli_worker_parses_defaults():
    with mock.patch.object(sys, "argv", ["lagomorph", "worker"]), mock.patch(
        "lagomorph.__main__._run_worker"
    ) as mock_run:
        main()
        args = mock_run.call_args[0][0]
        assert args.concurrency == 4
        assert args.poll_interval == 0.1
        assert args.task_timeout == 300


def test_cli_worker_parses_custom():
    with mock.patch.object(
        sys, "argv",
        ["lagomorph", "worker", "--concurrency", "8", "--poll-interval", "0.5", "--task-timeout", "600"],
    ), mock.patch("lagomorph.__main__._run_worker") as mock_run:
        main()
        args = mock_run.call_args[0][0]
        assert args.concurrency == 8
        assert args.poll_interval == 0.5
        assert args.task_timeout == 600


def test_cli_server_with_worker_flags():
    with mock.patch.object(
        sys, "argv",
        [
            "lagomorph", "server", "--worker",
            "--worker-concurrency", "8",
            "--worker-poll-interval", "0.5",
            "--worker-timeout", "600",
        ],
    ), mock.patch("lagomorph.__main__._run_server") as mock_run:
        main()
        args = mock_run.call_args[0][0]
        assert args.worker is True
        assert args.worker_concurrency == 8
        assert args.worker_poll_interval == 0.5
        assert args.worker_timeout == 600


def test_cli_server_worker_defaults():
    with mock.patch.object(sys, "argv", ["lagomorph", "server", "--worker"]), mock.patch(
        "lagomorph.__main__._run_server"
    ) as mock_run:
        main()
        args = mock_run.call_args[0][0]
        assert args.worker is True
        assert args.worker_concurrency == 4
        assert args.worker_poll_interval == 0.1
        assert args.worker_timeout == 300


def test_cli_requires_command():
    with mock.patch.object(sys, "argv", ["lagomorph"]):
        try:
            main()
            raise AssertionError("expected SystemExit")
        except SystemExit:
            pass


def test_cli_unknown_command():
    with mock.patch.object(sys, "argv", ["lagomorph", "unknown"]):
        try:
            main()
            raise AssertionError("expected SystemExit")
        except SystemExit:
            pass
