#!/usr/bin/env python3
"""OpenCanary -> hub event forwarder.

Tails OpenCanary's JSON log and posts a core.schema.Event-shaped dict to
`$HUB_URL/events` for every probe/connection. OpenCanary is a pure
multi-service tripwire (ftp/http/mysql/smb) -- no persona ever legitimately
talks to it, so every logged line here is attacker activity by construction.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forwarder import post_event, tail_json  # noqa: E402

OPENCANARY_LOG = os.environ.get("OPENCANARY_LOG", "/var/log/opencanary/opencanary.log")

# OpenCanary logtype ids -> (service, action). See opencanaryd/opencanary
# logger module for the full id table; we only need the services we enabled.
LOGTYPE_MAP = {
    2000: ("ftp", "login"),
    3000: ("http", "connect"),
    3001: ("http", "login"),
    4000: ("mysql", "connect"),
    4001: ("mysql", "login"),
    5000: ("smb", "connect"),
    5001: ("smb", "login"),
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(record: dict) -> dict | None:
    logtype = record.get("logtype")
    service, action = LOGTYPE_MAP.get(logtype, (record.get("logtype", "unknown"), "scan"))

    logdata = record.get("logdata", {}) or {}
    return {
        "source": "opencanary",
        "service": service if service in {"ftp", "http", "mysql", "smb"} else "http",
        "action": action,
        "src_ip": record.get("src_host", ""),
        "dst_host": "canary-multi",
        "identity": logdata.get("USERNAME"),
        "detail": {"logtype": logtype, **logdata},
        "raw": str(record),
        "ts": record.get("local_time_adjusted", record.get("local_time", utcnow_iso())),
    }


def main() -> None:
    for record in tail_json(OPENCANARY_LOG):
        event = build_event(record)
        if event is not None:
            post_event(event)


if __name__ == "__main__":
    main()
