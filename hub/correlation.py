"""Kill-chain correlation: group an attacker's alert events into an ordered
sequence and tag each step with a MITRE ATT&CK-style tactic + technique.

The goal is to turn a flat stream of alerts into a per-attacker story: what
they touched, in what order, and roughly how long they spent inside the
deception grid (their "dwell time"). Only ALERT events are considered -- benign
persona activity is noise for this view.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from core.schema import ALERT, Event


# --- ATT&CK mapping ----------------------------------------------------------
# (source, action) -> (tactic, technique). We match on the specific
# (source, action) pair first, then fall back to a source-only default, then a
# global "Unknown" fallback. Techniques are ATT&CK-style ids with a short human
# label appended for the dashboard.

_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("opencanary", "scan"): ("Reconnaissance", "T1595 Active Scanning"),
    ("opencanary", "connect"): ("Reconnaissance", "T1595 Active Scanning"),
    ("samba", "list_dir"): ("Discovery", "T1135 Network Share Discovery"),
    ("samba", "open_file"): ("Collection", "T1039 Data from Network Shared Drive"),
    ("samba", "download"): ("Collection", "T1039 Data from Network Shared Drive"),
    ("canarytoken", "token_trigger"): ("Exfiltration", "T1048 Exfiltration / canary tripped"),
    ("cowrie", "login"): ("Initial Access", "T1078 Valid Accounts"),
    ("cowrie", "command"): ("Execution", "T1059 Command & Scripting Interpreter"),
    ("intranet", "browse"): ("Discovery", "T1083 File & Directory Discovery (lured)"),
}

_SOURCE_DEFAULTS: dict[str, tuple[str, str]] = {
    "canarytoken": ("Exfiltration", "T1048 Exfiltration / canary tripped"),
    "opencanary": ("Reconnaissance", "T1595 Active Scanning"),
}

_FALLBACK: tuple[str, str] = ("Unknown", "-")


def tag(event: Event) -> tuple[str, str]:
    """Map an event's (source, action) to an ATT&CK (tactic, technique)."""
    pair = (event.source, event.action)
    if pair in _MAP:
        return _MAP[pair]
    if event.source in _SOURCE_DEFAULTS:
        return _SOURCE_DEFAULTS[event.source]
    return _FALLBACK


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _summarize(event: Event) -> str:
    """A compact one-line summary of an event's detail for the chain view."""
    if not event.detail:
        return ""
    parts = []
    for k, v in event.detail.items():
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def build_kill_chains(events: list[Event]) -> list[dict]:
    """Group ALERT events by src_ip into ordered per-attacker kill chains.

    Returns one dict per attacker, each shaped as::

        {"src_ip", "first_seen", "last_seen", "dwell_seconds", "steps": [...]}

    where each step is {ts, source, action, tactic, technique, detail_summary}.
    Chains are sorted by most recent activity (last_seen) first.
    """
    by_ip: dict[str, list[Event]] = defaultdict(list)
    for ev in events:
        if ev.classification != ALERT or not ev.src_ip:
            continue
        by_ip[ev.src_ip].append(ev)

    chains: list[dict] = []
    for src_ip, evs in by_ip.items():
        ordered = sorted(evs, key=lambda e: e.ts)
        steps = []
        for ev in ordered:
            tactic, technique = tag(ev)
            steps.append({
                "ts": ev.ts,
                "source": ev.source,
                "action": ev.action,
                "tactic": tactic,
                "technique": technique,
                "detail_summary": _summarize(ev),
            })

        first_ts = ordered[0].ts
        last_ts = ordered[-1].ts
        first_dt = _parse_ts(first_ts)
        last_dt = _parse_ts(last_ts)
        if first_dt is not None and last_dt is not None:
            dwell_seconds = (last_dt - first_dt).total_seconds()
        else:
            dwell_seconds = 0.0

        chains.append({
            "src_ip": src_ip,
            "first_seen": first_ts,
            "last_seen": last_ts,
            "dwell_seconds": dwell_seconds,
            "steps": steps,
        })

    chains.sort(key=lambda c: c["last_seen"], reverse=True)
    return chains
