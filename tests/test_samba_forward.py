"""Unit tests for the Samba full_audit -> hub forwarder parser."""

import importlib.util
from pathlib import Path

# Load the sidecar module directly (it lives under traps/, not a package).
_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "samba_forward", _ROOT / "traps" / "fileserver" / "samba_forward.py"
)
samba_forward = importlib.util.module_from_spec(_spec)
# Make the shared helper importable the way the module expects.
import sys
sys.path.insert(0, str(_ROOT / "traps"))
_spec.loader.exec_module(samba_forward)

# A real audit line captured from the running lab.
LINE = ("2026-08-12T19:40:28.177746+00:00 host smbd_audit: "
        "nobody|172.18.0.11|company|openat|ok|r|/share/it/passwords.xlsx")
DIR_LINE = ("... smbd_audit: nobody|172.18.0.11|company|openat|ok|r|/share/finance")
WRITE_LINE = ("... smbd_audit: nobody|10.0.0.5|company|unlink|fail|/share/x")


def test_parses_file_open_and_strips_share_prefix():
    p = samba_forward.parse_audit_line(LINE)
    assert p is not None
    assert p["ip"] == "172.18.0.11"
    assert p["path"] == "it/passwords.xlsx"  # /share/ prefix stripped


def test_ignores_directory_opens():
    assert samba_forward.parse_audit_line(DIR_LINE) is None


def test_ignores_non_open_ops():
    assert samba_forward.parse_audit_line(WRITE_LINE) is None


def test_canary_match_emits_token_trigger():
    parsed = {"user": "nobody", "ip": "1.2.3.4", "share": "company",
              "op": "openat", "path": "it/passwords.xlsx"}
    canaries = {"it/passwords.xlsx": "CANARY-TOKEN:abc"}
    events = samba_forward.build_events(parsed, canaries)
    sources = [e["source"] for e in events]
    assert "samba" in sources and "canarytoken" in sources
    trip = next(e for e in events if e["source"] == "canarytoken")
    assert trip["detail"]["token_id"] == "CANARY-TOKEN:abc"
    assert trip["action"] == "token_trigger"


def test_non_canary_file_only_samba_event():
    parsed = {"user": "nobody", "ip": "1.2.3.4", "share": "company",
              "op": "openat", "path": "hr/org_chart.pptx"}
    events = samba_forward.build_events(parsed, {"it/passwords.xlsx": "t"})
    assert [e["source"] for e in events] == ["samba"]


def test_canary_match_by_basename():
    parsed = {"user": "nobody", "ip": "9.9.9.9", "share": "company",
              "op": "openat", "path": "it/passwords.xlsx"}
    # Manifest path differs in dir but same basename -> still trips.
    canaries = {"backup/passwords.xlsx": "CANARY-TOKEN:xyz"}
    events = samba_forward.build_events(parsed, canaries)
    assert any(e["source"] == "canarytoken" for e in events)
