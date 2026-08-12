"""Action -> Event mapping (and optional real network I/O) for the persona engine.

Every simulated employee behaviour is expressed as one of the shared
`core.schema.ACTIONS`. This module owns two things:

  * `build_event()` — the pure, offline-safe translation of an action into a
    `core.schema.Event`. It never touches the network, so it works in tests and
    in the offline demo.
  * `perform()`   — build the event, *optionally* attempt the corresponding real
    protocol interaction (SMB/HTTP/SMTP/SSH) against the lab services, then emit
    it to the sink. Real I/O is strictly best-effort: any failure is swallowed
    and recorded in the event's `detail`, so telemetry never stops flowing just
    because a decoy container is down.

Events are stamped `classification="unknown"`; the hub's detection engine is the
only component allowed to decide what is benign.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Persona
from core.schema import Event, UNKNOWN

# --- Action taxonomy --------------------------------------------------------
# Which service each simulated action speaks. Keys are a subset of
# core.schema.ACTIONS; values are a subset of core.schema.SERVICES.
SERVICE_BY_ACTION: dict[str, str] = {
    "open_file": "smb",
    "edit_file": "smb",
    "close_file": "smb",
    "share_file": "smb",
    "list_dir": "smb",
    "browse": "http",
    "send_mail": "smtp",
    "ssh": "ssh",
    "login": "ssh",
    "logout": "ssh",
}

# `ssh` is not itself in core.schema.ACTIONS (it is "login" on the jumphost),
# but the persona config uses it as an activity weight; we emit it as a `login`
# action against the jumphost while keeping the intent in `detail["activity"]`.
ACTION_ALIASES: dict[str, str] = {"ssh": "login"}

# Which decoy host answers each service (container names in the lab network).
HOST_BY_SERVICE: dict[str, str] = {
    "smb": os.environ.get("SMB_HOST", "fileserver"),
    "http": os.environ.get("INTRANET_HOST", "intranet"),
    "smtp": os.environ.get("MAIL_HOST", "mail"),
    "ssh": os.environ.get("JUMPHOST", "jumphost"),
}

# Plausible intranet paths a persona browses during the day.
INTRANET_PATHS = (
    "/", "/news", "/hr/policies", "/it/helpdesk", "/directory",
    "/finance/reports", "/wiki/onboarding", "/timesheets",
)

# Plausible internal mail subjects.
MAIL_SUBJECTS = (
    "Re: weekly status", "Q3 numbers", "Invoice approval",
    "Meeting notes", "Access request", "Vacation cover", "Deploy window",
)

SHELL_COMMANDS = ("uptime", "df -h", "systemctl status ssh", "tail -n 50 /var/log/syslog")


def _service_for(action: str) -> str:
    return SERVICE_BY_ACTION.get(action, "http")


def _pick(rng: Optional[random.Random], seq) -> Any:
    r = rng or random
    return r.choice(list(seq))


# Which file each persona currently has open, so an open -> edit -> close burst
# refers to one consistent document instead of three unrelated ones.
_OPEN_FILES: dict[str, str] = {}


def _file_for(action: str, persona: Persona, rng: Optional[random.Random]) -> str:
    """A file this persona legitimately owns, relative to their share."""
    if action in ("edit_file", "close_file") and persona.username in _OPEN_FILES:
        chosen = _OPEN_FILES[persona.username]
    elif persona.files_owned:
        chosen = _pick(rng, persona.files_owned)
    else:
        chosen = f"{persona.username}/notes.txt"

    if action == "open_file":
        _OPEN_FILES[persona.username] = chosen
    elif action == "close_file":
        _OPEN_FILES.pop(persona.username, None)
    return chosen


def _share_path(persona: Persona, host: str, rel: str) -> str:
    """UNC-style path, without repeating the share name already in `rel`."""
    prefix = f"{persona.smb_share}/"
    tail = rel[len(prefix):] if rel.startswith(prefix) else rel
    return f"//{host}/{persona.smb_share}/{tail}"


def build_event(
    action: str,
    persona: Persona,
    ts: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> Event:
    """Translate one persona action into an `Event`.

    `ts` lets the caller back-date an event (the day planner emits a whole
    workday at once); it is normalised to a UTC ISO-8601 string.
    """
    service = _service_for(action)
    dst_host = HOST_BY_SERVICE.get(service, "")
    detail: dict[str, Any] = {"role": persona.role, "activity": action}

    if service == "smb":
        rel = _file_for(action, persona, rng)
        detail["share"] = persona.smb_share
        detail["file"] = rel
        detail["path"] = _share_path(persona, dst_host, rel)
        if action == "share_file":
            detail["shared_with"] = f"{persona.username}-team"
    elif service == "http":
        path = _pick(rng, INTRANET_PATHS)
        detail["url"] = f"http://{dst_host}{path}"
        detail["method"] = "GET"
    elif service == "smtp":
        detail["subject"] = _pick(rng, MAIL_SUBJECTS)
        detail["to"] = f"team@{dst_host}"
        detail["from"] = persona.username
    elif service == "ssh":
        detail["host"] = dst_host
        if action == "ssh":
            detail["command"] = _pick(rng, SHELL_COMMANDS)

    emitted_action = ACTION_ALIASES.get(action, action)

    ev = Event(
        source="persona",
        service=service,
        action=emitted_action,
        src_ip=persona.home_ip,
        dst_host=dst_host,
        identity=persona.username,
        detail=detail,
        raw=f"{persona.username}@{persona.home_ip} {emitted_action} {service}",
        classification=UNKNOWN,
    )
    if ts is not None:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ev.ts = ts.astimezone(timezone.utc).isoformat()
    return ev


# --- Best-effort real I/O ---------------------------------------------------
# Only used in the lab (live=True). Every call is wrapped: a broken or missing
# decoy service must never interrupt event emission.

def _io_smb(event: Event) -> None:
    import subprocess

    host = event.dst_host
    share = event.detail.get("share", "share")
    # Path relative to the share root, as smbclient expects it.
    path = event.detail.get("path", "").split(f"/{share}/", 1)[-1]
    cmd = {"open_file": f'get "{path}" /dev/null', "edit_file": f'get "{path}" /dev/null'}.get(
        event.detail.get("activity", ""), "ls"
    )
    subprocess.run(
        ["smbclient", f"//{host}/{share}", "-N", "-c", cmd],
        capture_output=True, timeout=10, check=False,
    )


def _io_http(event: Event) -> None:
    import requests  # type: ignore[import-untyped]

    requests.get(event.detail.get("url", f"http://{event.dst_host}/"), timeout=5)


def _io_smtp(event: Event) -> None:
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = f"{event.identity}@{os.environ.get('MAIL_DOMAIN', 'lab.local')}"
    msg["To"] = event.detail.get("to", "team@lab.local")
    msg["Subject"] = event.detail.get("subject", "(no subject)")
    msg.set_content("Synthetic internal mail generated by the persona engine.")
    with smtplib.SMTP(event.dst_host, int(os.environ.get("SMTP_PORT", "1025")), timeout=5) as s:
        s.send_message(msg)


def _io_ssh(event: Event) -> None:
    import paramiko  # type: ignore[import-untyped]

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            event.dst_host,
            username=event.identity or "user",
            password=os.environ.get("JUMPHOST_PASSWORD", "labpass"),
            timeout=5, allow_agent=False, look_for_keys=False,
        )
        cmd = event.detail.get("command")
        if cmd:
            client.exec_command(cmd, timeout=5)
    finally:
        client.close()


_IO_BY_SERVICE = {"smb": _io_smb, "http": _io_http, "smtp": _io_smtp, "ssh": _io_ssh}


def attempt_io(event: Event) -> bool:
    """Try the real protocol interaction for `event`. Never raises.

    Returns True on success. The outcome is recorded in `event.detail["live"]`
    so the dashboard can tell simulated-only from genuinely-observed traffic.
    """
    handler = _IO_BY_SERVICE.get(event.service)
    if handler is None:
        return False
    try:
        handler(event)
        event.detail["live"] = "ok"
        return True
    except Exception as exc:  # noqa: BLE001 - best effort by design
        event.detail["live"] = "failed"
        event.detail["live_error"] = f"{type(exc).__name__}: {exc}"[:200]
        return False


def perform(
    action: str,
    persona: Persona,
    sink,
    live: bool = False,
    ts: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> Event:
    """Build the event for `action`, optionally do real I/O, then emit it."""
    event = build_event(action, persona, ts=ts, rng=rng)
    if live:
        attempt_io(event)
    try:
        sink.emit(event)
    except Exception as exc:  # noqa: BLE001 - a dead hub must not kill the engine
        print(f"[personas] emit failed ({type(exc).__name__}: {exc})", flush=True)
    return event
