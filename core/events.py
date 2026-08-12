"""Event emission helper used by producers (personas, attacker sim, trap tailers).

Two sinks, chosen by environment:

  * HttpSink  -> POST to the hub's /events endpoint (container/lab mode).
                 Enabled when HUB_URL is set (e.g. http://hub:8000).
  * DirectSink -> write straight into the SQLite store (local/dry-run/tests).
                 Used when HUB_URL is unset; path from EVENTS_DB or the default.

This lets the persona engine and attacker sim run fully offline (no containers)
for development and verification, while the exact same code posts to the hub in
the real lab.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

from core.schema import Event, connect, insert_event, DEFAULT_DB


class DirectSink:
    """Write events directly to the SQLite store."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("EVENTS_DB", DEFAULT_DB)
        self._conn = connect(self.db_path)

    def emit(self, event: Event) -> None:
        insert_event(self._conn, event)

    def close(self) -> None:
        self._conn.close()


class HttpSink:
    """POST events to the hub ingest endpoint."""

    def __init__(self, hub_url: Optional[str] = None):
        self.hub_url = (hub_url or os.environ["HUB_URL"]).rstrip("/")

    def emit(self, event: Event) -> None:
        payload = json.dumps(event.as_dict()).encode()
        req = urllib.request.Request(
            f"{self.hub_url}/events", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=5).read()

    def close(self) -> None:  # symmetry with DirectSink
        pass


def get_sink() -> "DirectSink | HttpSink":
    """Pick a sink based on environment. HUB_URL wins if present."""
    if os.environ.get("HUB_URL"):
        return HttpSink()
    return DirectSink()
