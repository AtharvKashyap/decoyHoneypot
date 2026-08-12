"""Detection engine: classify events as benign / alert / unknown.

Rules (see spec for rationale):

  * Pure trap sources (cowrie, opencanary, canarytoken) are never touched by
    legitimate personas -> any hit is an ALERT. canarytoken hits (and any
    action == "token_trigger") are CRITICAL; other trap hits are HIGH.
  * persona-source events are only benign if they match a *real* persona's
    identity, home IP, and work-hours window -- otherwise treat them as an
    identity/schedule anomaly (e.g. a replayed persona account) -> ALERT/HIGH.
  * Real usable services (samba, intranet, jumphost, mail) are benign only if
    the source IP belongs to a known persona AND falls within that persona's
    work-hours window. Otherwise it's an unknown actor on a real service ->
    ALERT/MEDIUM.
  * Anything else is UNKNOWN/INFO (not yet classifiable).
"""

from __future__ import annotations

from datetime import datetime, time as dtime

from core.config import Company, Persona
from core.schema import (
    Event,
    ALERT,
    BENIGN,
    UNKNOWN,
    INFO,
    MEDIUM,
    HIGH,
    CRITICAL,
    connect,
    query_events,
)

TRAP_SOURCES = ("cowrie", "opencanary", "canarytoken")
REAL_SERVICE_SOURCES = ("samba", "intranet", "jumphost", "mail")


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp (with or without timezone) into a naive
    datetime we can compare against HH:MM work-hour boundaries."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")
    return dtime(int(hh), int(mm))


def _within_hours(persona: Persona, dt: datetime) -> bool:
    """True if `dt` falls within the persona's configured work window."""
    wh = persona.work_hours
    if dt.weekday() not in wh.days:
        return False
    start = _parse_hhmm(wh.start)
    end = _parse_hhmm(wh.end)
    t = dt.time()
    return start <= t <= end


def classify(event: Event, company: Company) -> tuple[str, str]:
    """Return (classification, severity) for `event` given the company's
    known-persona baseline."""

    if event.source in TRAP_SOURCES:
        if event.source == "canarytoken" or event.action == "token_trigger":
            return ALERT, CRITICAL
        return ALERT, HIGH

    if event.source == "persona":
        persona = company.persona_by_username(event.identity) if event.identity else None
        if persona is not None and event.src_ip == persona.home_ip:
            try:
                dt = _parse_ts(event.ts)
            except (ValueError, TypeError):
                dt = None
            if dt is not None and _within_hours(persona, dt):
                return BENIGN, INFO
        return ALERT, HIGH

    if event.source in REAL_SERVICE_SOURCES:
        persona = company.persona_by_ip(event.src_ip) if event.src_ip else None
        if persona is not None:
            try:
                dt = _parse_ts(event.ts)
            except (ValueError, TypeError):
                dt = None
            if dt is not None and _within_hours(persona, dt):
                return BENIGN, INFO
        return ALERT, MEDIUM

    return UNKNOWN, INFO


def classify_store(db_path: str, company: Company) -> int:
    """Classify every 'unknown' event in the store at `db_path`, updating it
    in place. Returns the number of rows updated."""
    conn = connect(db_path)
    try:
        unknown_events = query_events(conn, classification=UNKNOWN, limit=10_000_000)
        updated = 0
        for ev in unknown_events:
            classification, severity = classify(ev, company)
            conn.execute(
                "UPDATE events SET classification = ?, severity = ? WHERE id = ?",
                (classification, severity, ev.id),
            )
            updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()
