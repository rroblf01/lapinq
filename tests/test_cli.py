from __future__ import annotations

import argparse
import uuid

from lapinq.__main__ import _add_task_cancel_parser, _add_task_get_parser, _add_task_list_parser, _add_task_requeue_parser


def _make_task_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lapinq task")
    sub = p.add_subparsers(dest="task_command", required=True)
    _add_task_list_parser(sub)
    _add_task_get_parser(sub)
    _add_task_cancel_parser(sub)
    _add_task_requeue_parser(sub)
    return p


def test_task_list_parser():
    p = _make_task_parser()
    args = p.parse_args(["list"])
    assert args.task_command == "list"
    assert args.queue is None
    assert args.status is None
    assert args.limit == 20


def test_task_list_with_flags():
    p = _make_task_parser()
    args = p.parse_args(["list", "--queue", "video", "--status", "failed", "--limit", "5"])
    assert args.queue == "video"
    assert args.status == "failed"
    assert args.limit == 5


def test_task_list_short_flags():
    p = _make_task_parser()
    args = p.parse_args(["list", "-q", "audio", "-s", "completed", "-l", "50"])
    assert args.queue == "audio"
    assert args.status == "completed"
    assert args.limit == 50


def test_task_list_json():
    p = _make_task_parser()
    args = p.parse_args(["list", "--json"])
    assert args.json is True


def test_task_get_parser():
    p = _make_task_parser()
    tid = str(uuid.uuid4())
    args = p.parse_args(["get", tid])
    assert args.task_command == "get"
    assert args.task_id == tid


def test_task_get_json():
    p = _make_task_parser()
    tid = str(uuid.uuid4())
    args = p.parse_args(["get", tid, "--json"])
    assert args.json is True


def test_task_cancel_parser():
    p = _make_task_parser()
    tid = str(uuid.uuid4())
    args = p.parse_args(["cancel", tid])
    assert args.task_command == "cancel"
    assert args.task_id == tid


def test_task_requeue_parser():
    p = _make_task_parser()
    tid = str(uuid.uuid4())
    args = p.parse_args(["requeue", tid])
    assert args.task_command == "requeue"
    assert args.task_id == tid


def test_server_parser():
    from lapinq.__main__ import build_parser

    parser = build_parser()
    args = parser.parse_args(["server", "--port", "9999", "--log-level", "debug"])
    assert args.command == "server"
    assert args.port == 9999
    assert args.log_level == "debug"
