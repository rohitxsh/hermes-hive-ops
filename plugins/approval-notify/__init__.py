"""Queue a note whenever an agent starts waiting for its owner: a command approval, a question it asked,
or a Kanban task blocked on a human. The "approval notify" cron job (every minute, no LLM) pings the
owner in #assistant for anything still unanswered after 3 minutes, so requests aren't lost
in a busy channel. Writes one small JSON line per event to ~/.hermes/approval-queue.jsonl (prompts are
already redacted by Hermes)."""
from __future__ import annotations

import fcntl
import json
import os
import time

QUEUE = os.path.expanduser("~/.hermes/approval-queue.jsonl")


def _profile() -> str:
    try:
        from hermes_constants import get_hermes_home
        home = os.path.realpath(str(get_hermes_home()))
        return "default" if home == os.path.realpath(os.path.expanduser("~/.hermes")) else os.path.basename(home)
    except Exception:
        return "?"


def _append(record: dict) -> None:
    record.update(at=time.time(), profile=_profile())
    try:
        with open(QUEUE, "a") as fh:  # several gateway threads and Kanban worker processes append here
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass  # a notification must never break a prompt


def on_human_input_request(**p) -> None:
    _append({"event": "request", "id": p.get("request_id"), "kind": p.get("kind"),
             "session_key": p.get("session_key") or "", "platform": p.get("platform") or "",
             "prompt": str(p.get("prompt") or "")[:300]})


def on_human_input_resolved(**p) -> None:
    _append({"event": "resolved", "id": p.get("request_id"), "outcome": p.get("outcome")})


def kanban_task_blocked(**p) -> None:
    _append({"event": "kanban_blocked", "id": f"kanban:{p.get('task_id')}:{int(time.time())}",
             "task_id": p.get("task_id"), "assignee": p.get("assignee"), "reason": str(p.get("reason") or "")[:300]})


def register(ctx) -> None:
    ctx.register_hook("on_human_input_request", on_human_input_request)
    ctx.register_hook("on_human_input_resolved", on_human_input_resolved)
    ctx.register_hook("kanban_task_blocked", kanban_task_blocked)
