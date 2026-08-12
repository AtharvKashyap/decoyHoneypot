#!/usr/bin/env python3
"""Samba full_audit -> hub event forwarder (fileserver sidecar).

Tails the rsyslog-captured Samba audit log and, for every successful file
OPEN, posts a `samba` event to the hub. If the opened file is one of the
canaried decoy documents (per seed/generated/canary_manifest.json), it ALSO
posts a `canarytoken` `token_trigger` event — the file-based canary firing the
instant a sensitive document is read off the share.

The fileserver is a real, usable share; in the lab the persona engine emits its
benign file activity directly to the hub (PERSONA_LIVE=0), so any *real* SMB
open observed here is an intruder pulling decoy files.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forwarder import post_event  # noqa: E402  (shared stdlib-only helper)

AUDIT_LOG = os.environ.get("AUDIT_LOG", "/var/log/samba/audit/audit.log")
CANARY_MANIFEST = os.environ.get("CANARY_MANIFEST", "/seed/canary_manifest.json")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_canary_paths() -> dict[str, str]:
    """Return {relative_doc_path: token} for canaried documents, if available."""
    p = Path(CANARY_MANIFEST)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    tokens = data.get("tokens") or {}
    # Manifest is {token: path}; invert to {path: token} (and index by basename too).
    out: dict[str, str] = {}
    if isinstance(tokens, dict):
        for token, path in tokens.items():
            out[str(path)] = str(token)
    return out


def parse_audit_line(line: str) -> dict | None:
    """Parse one Samba full_audit syslog line into a dict, or None if it is not
    a successful file-open we care about.

    full_audit prefix is `%u|%I|%S`, so the audited message looks like:
        <syslog preamble> user|ip|share|openat|ok|<path args...>
    Path extraction is defensive: Samba versions differ in how many arg fields
    they log, so we take the last path-looking token.
    """
    marker = "smbd_audit:"
    idx = line.find(marker)
    payload = line[idx + len(marker):].strip() if idx != -1 else line.strip()

    parts = [p.strip() for p in payload.split("|")]
    if len(parts) < 5:
        return None
    user, ip, share, op, result = parts[0], parts[1], parts[2], parts[3], parts[4]
    if op != "openat" or result != "ok":
        return None

    args = [a for a in parts[5:] if a]
    # The real filename is the last token that looks like a path with a file
    # extension; skip pure directories, ".", "..", and fd markers.
    path = ""
    for tok in reversed(args):
        base = tok.rstrip("/").split("/")[-1]
        if "." in base and base not in (".", ".."):
            path = tok.lstrip("/")
            break
    if not path:
        return None
    # Strip the share mount root (/share) so the path matches the canary
    # manifest keys, which are relative to the share (e.g. it/passwords.xlsx).
    if path.startswith("share/"):
        path = path[len("share/"):]
    return {"user": user, "ip": ip, "share": share, "op": op, "path": path}


def build_events(parsed: dict, canaries: dict[str, str]) -> list[dict]:
    """Build the hub event(s) for one parsed open: a samba open_file, plus a
    canarytoken token_trigger if the path matches a canaried document."""
    path = parsed["path"]
    ip = parsed["ip"]
    events: list[dict] = [{
        "source": "samba",
        "service": "smb",
        "action": "open_file",
        "src_ip": ip,
        "dst_host": "fileserver",
        "identity": parsed.get("user") or None,
        "detail": {"path": path, "share": parsed.get("share")},
        "raw": f"smb_audit: openat ok {path} from {ip}",
        "ts": utcnow_iso(),
    }]
    # Match by full relative path or by basename (robust across path formats).
    token = canaries.get(path)
    if token is None:
        base = path.split("/")[-1]
        for doc_path, tok in canaries.items():
            if doc_path.split("/")[-1] == base:
                token, path = tok, doc_path
                break
    if token is not None:
        events.append({
            "source": "canarytoken",
            "service": "http",
            "action": "token_trigger",
            "src_ip": ip,
            "dst_host": "canary-service",
            "detail": {"token_id": token, "document": path,
                       "note": "canaried document read off the SMB share"},
            "raw": f"canarytoken: trigger {token} (doc={path}) from {ip}",
            "ts": utcnow_iso(),
        })
    return events


def main() -> None:
    canaries = load_canary_paths()
    print(f"[samba_forward] loaded {len(canaries)} canary paths; tailing {AUDIT_LOG}")
    seen: set[tuple[str, str]] = set()
    for line in tail_lines(AUDIT_LOG):
        parsed = parse_audit_line(line)
        if not parsed:
            continue
        key = (parsed["ip"], parsed["path"])
        if key in seen:
            continue
        seen.add(key)
        for event in build_events(parsed, canaries):
            post_event(event)


def tail_lines(path: str, poll_interval: float = 0.5):
    """Follow a plain text log file like `tail -F`, yielding raw lines."""
    import time
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
            yield line.rstrip("\n")


if __name__ == "__main__":
    main()
