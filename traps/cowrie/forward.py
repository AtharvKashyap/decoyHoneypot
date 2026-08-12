#!/usr/bin/env python3
"""Cowrie -> hub event forwarder.

Tails Cowrie's JSON event log (`var/log/cowrie/cowrie.json`) and posts a
core.schema.Event-shaped dict to `$HUB_URL/events` for each interesting
Cowrie eventid:

  cowrie.login.success / cowrie.login.failed  -> action "login"
  cowrie.command.input                        -> action "command"
  cowrie.session.connect                       -> action "connect"

Cowrie is a *pure trap*: nothing legitimate ever reaches it, so every event
forwarded here is, by construction, attacker activity. Runs as a sidecar
process inside the cowrie container (see entrypoint.sh).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forwarder import post_event, tail_json  # noqa: E402

COWRIE_LOG = os.environ.get(
    "COWRIE_LOG", "/cowrie/cowrie-git/var/log/cowrie/cowrie.json"
)

EVENTID_TO_ACTION = {
    "cowrie.login.success": "login",
    "cowrie.login.failed": "login",
    "cowrie.command.input": "command",
    "cowrie.session.connect": "connect",
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(record: dict) -> dict | None:
    eventid = record.get("eventid", "")
    action = EVENTID_TO_ACTION.get(eventid)
    if action is None:
        return None

    detail = {"eventid": eventid, "session": record.get("session")}
    if action == "login":
        detail["username"] = record.get("username")
        detail["password"] = record.get("password")
        detail["success"] = eventid == "cowrie.login.success"
    elif action == "command":
        detail["input"] = record.get("input")

    return {
        "source": "cowrie",
        "service": "ssh" if record.get("protocol", "ssh") != "telnet" else "telnet",
        "action": action,
        "src_ip": record.get("src_ip", ""),
        "dst_host": "cowrie-ssh",
        "identity": record.get("username"),
        "detail": detail,
        "raw": record.get("message", str(record)),
        "ts": record.get("timestamp", utcnow_iso()),
    }


def main() -> None:
    for record in tail_json(COWRIE_LOG):
        event = build_event(record)
        if event is not None:
            post_event(event)


if __name__ == "__main__":
    main()
