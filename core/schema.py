"""Shared event-store schema and access helpers.

This module is the single source of truth for the event model used across the
whole deception grid. Every component depends on it:

  * personas/  -> emit benign activity events
  * traps/     -> attacker interactions arrive as events
  * hub/       -> ingests, classifies, and renders events

An "event" is any observed interaction on the deception network. The detection
engine later stamps each event with a `classification` and `severity`.

Design choices:
  * SQLite: zero-config, single-file, perfect for a one-host lab and tests.
  * WAL mode: lets the persona engine write while the dashboard reads.
  * A plain dataclass + explicit columns (no ORM) keeps the contract obvious.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# --- Controlled vocabularies -------------------------------------------------
# These are strings (not enums) so log tailers and external tools can populate
# them freely, but the canonical values live here for everyone to reference.

# Where the event was observed.
SOURCES = (
    "persona",      # simulated employee (known-benign by construction)
    "cowrie",       # SSH/Telnet honeypot (pure trap)
    "opencanary",   # multi-service tripwire (pure trap)
    "canarytoken",  # decoy-file callback (pure trap)
    "samba",        # real fileserver used by personas AND discoverable by attackers
    "intranet",     # fake internal web portal
    "mail",         # fake mail server
    "jumphost",     # plain SSH host personas use
)

# The protocol/service involved.
SERVICES = ("ssh", "smb", "http", "ftp", "mysql", "smtp", "file", "telnet")

# What happened.
ACTIONS = (
    "login", "logout", "command", "connect", "scan",
    "open_file", "edit_file", "close_file", "share_file", "list_dir",
    "browse", "send_mail", "token_trigger", "download",
)

# Detection outcomes.
BENIGN = "benign"      # matches a known persona baseline
ALERT = "alert"        # attacker activity (trap hit or off-baseline)
UNKNOWN = "unknown"    # not yet classified
CLASSIFICATIONS = (BENIGN, ALERT, UNKNOWN)

# Severity ladder for alerts (benign events are INFO).
INFO, LOW, MEDIUM, HIGH, CRITICAL = "info", "low", "medium", "high", "critical"
SEVERITIES = (INFO, LOW, MEDIUM, HIGH, CRITICAL)


def utcnow_iso() -> str:
    """ISO-8601 UTC timestamp, e.g. '2026-08-12T09:03:11.204512+00:00'."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Event:
    """One observed interaction on the deception network."""

    source: str                       # one of SOURCES
    service: str                      # one of SERVICES
    action: str                       # one of ACTIONS
    src_ip: str = ""                  # observed source IP
    dst_host: str = ""                # target decoy host/service name
    identity: Optional[str] = None    # persona username if known, else None
    detail: dict[str, Any] = field(default_factory=dict)  # structured context
    raw: str = ""                     # original log line / payload
    ts: str = field(default_factory=utcnow_iso)
    classification: str = UNKNOWN
    severity: str = INFO
    id: Optional[int] = None          # set once persisted

    def to_row(self) -> tuple:
        return (
            self.ts, self.source, self.service, self.action, self.src_ip,
            self.dst_host, self.identity, json.dumps(self.detail), self.raw,
            self.classification, self.severity,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    source         TEXT NOT NULL,
    service        TEXT NOT NULL,
    action         TEXT NOT NULL,
    src_ip         TEXT DEFAULT '',
    dst_host       TEXT DEFAULT '',
    identity       TEXT,
    detail         TEXT DEFAULT '{}',
    raw            TEXT DEFAULT '',
    classification TEXT DEFAULT 'unknown',
    severity       TEXT DEFAULT 'info'
);
CREATE INDEX IF NOT EXISTS idx_events_ts             ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_classification ON events(classification);
CREATE INDEX IF NOT EXISTS idx_events_src_ip         ON events(src_ip);
"""

DEFAULT_DB = "data/events.db"


def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    """Open (creating parent dir if needed) and initialize the event store."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(CREATE_SQL)
    return conn


def insert_event(conn: sqlite3.Connection, event: Event) -> int:
    """Persist an event, returning its new row id."""
    cur = conn.execute(
        """INSERT INTO events
           (ts, source, service, action, src_ip, dst_host, identity,
            detail, raw, classification, severity)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        event.to_row(),
    )
    conn.commit()
    event.id = cur.lastrowid
    return cur.lastrowid


def row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"], ts=row["ts"], source=row["source"], service=row["service"],
        action=row["action"], src_ip=row["src_ip"], dst_host=row["dst_host"],
        identity=row["identity"], detail=json.loads(row["detail"] or "{}"),
        raw=row["raw"], classification=row["classification"], severity=row["severity"],
    )


def query_events(
    conn: sqlite3.Connection,
    classification: Optional[str] = None,
    limit: int = 500,
) -> list[Event]:
    sql = "SELECT * FROM events"
    params: list[Any] = []
    if classification:
        sql += " WHERE classification = ?"
        params.append(classification)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [row_to_event(r) for r in conn.execute(sql, params).fetchall()]
