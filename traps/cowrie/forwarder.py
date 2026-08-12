#!/usr/bin/env python3
"""Shared helper used by trap sidecars (cowrie, opencanary, ...) to forward
attacker-observed log lines into the hub's event store.

Deliberately dependency-light (stdlib `urllib` only, no `requests`) so it can
be dropped into any minimal trap container image without adding a Python
dependency to the build. Trap containers are internet-isolated (see
docker-compose.yml `deception` network, `internal: true`); the only network
call this module ever makes is to `$HUB_URL`, which is reachable on that same
internal network.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator


def post_event(event_dict: dict[str, Any], hub_url: str | None = None,
                timeout: float = 5.0) -> None:
    """POST a single event dict (shaped like core.schema.Event.as_dict()) to
    the hub's /events endpoint.

    `hub_url` defaults to the HUB_URL environment variable (set by
    docker-compose for every trap service). Swallows connection errors after
    logging to stderr -- a forwarder hiccup must never crash the trap it is
    attached to.
    """
    url = (hub_url or os.environ.get("HUB_URL", "")).rstrip("/")
    if not url:
        raise RuntimeError("HUB_URL is not set; forwarder has nowhere to post events")

    payload = json.dumps(event_dict).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/events",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=timeout).read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"[forwarder] failed to POST event to {url}/events: {exc}")


def tail_json(path: str, poll_interval: float = 0.5) -> Iterator[dict[str, Any]]:
    """Follow a newline-delimited JSON log file (like `tail -F`) and yield
    each decoded JSON object as it is appended.

    Waits for the file to exist (Cowrie/OpenCanary may not have created their
    log yet at sidecar startup), then seeks to EOF and streams new lines
    forever. Malformed lines are skipped rather than raising, since a broken
    line must never take the forwarder down.
    """
    p = Path(path)
    while not p.exists():
        time.sleep(poll_interval)

    with p.open("r") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            line = fh.readline()
            if not line:
                time.sleep(poll_interval)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: forwarder.py <path-to-json-log>", file=sys.stderr)
        raise SystemExit(1)

    for record in tail_json(sys.argv[1]):
        print(f"[forwarder] tailed record: {record}")
