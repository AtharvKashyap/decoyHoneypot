"""Ingest helpers shared by the FastAPI app: DB connection + event insertion.

The store path is read from EVENTS_DB *at call time* (not at import time) so
tests can point it at a tmp file via monkeypatch.setenv before making
requests, without needing to reload/reimport the app module.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from core.config import Company, load_company
from core.schema import DEFAULT_DB, Event, connect, insert_event
from hub.detection import classify


def get_db_path() -> str:
    return os.environ.get("EVENTS_DB", DEFAULT_DB)


def get_conn() -> sqlite3.Connection:
    """Open a fresh connection to the current EVENTS_DB. Callers are
    responsible for closing it (or use it in a `with`-style scope)."""
    return connect(get_db_path())


def get_company() -> Company:
    """Load the current company config fresh, so config changes and test
    fixtures are picked up per-request."""
    return load_company()


def ingest_event(event: Event, conn: sqlite3.Connection | None = None,
                  company: Company | None = None) -> int:
    """Classify and persist a single event. Returns its row id."""
    own_conn = conn is None
    if conn is None:
        conn = get_conn()
    if company is None:
        company = get_company()
    try:
        classification, severity = classify(event, company)
        event.classification = classification
        event.severity = severity
        return insert_event(conn, event)
    finally:
        if own_conn:
            conn.close()


def event_from_dict(payload: dict[str, Any]) -> Event:
    """Build an Event from a JSON payload shaped like Event.as_dict(), being
    forgiving about missing/extra keys (e.g. `id` should not be pre-set)."""
    payload = dict(payload)
    payload.pop("id", None)
    known_fields = {
        "source", "service", "action", "src_ip", "dst_host", "identity",
        "detail", "raw", "ts", "classification", "severity",
    }
    kwargs = {k: v for k, v in payload.items() if k in known_fields}
    kwargs.setdefault("source", "")
    kwargs.setdefault("service", "")
    kwargs.setdefault("action", "")
    return Event(**kwargs)
