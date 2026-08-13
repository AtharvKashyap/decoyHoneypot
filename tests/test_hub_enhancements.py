"""Tests for the hub enhancements: kill-chain correlation, canary HTTP
callback, and outbound alerting."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from core.schema import (
    ALERT,
    BENIGN,
    CRITICAL,
    INFO,
    connect,
    insert_event,
    Event,
    query_events,
)
from hub.correlation import build_kill_chains, tag
from hub.notify import notify

MONDAY_10AM = "2026-08-10T10:00:00"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "events.db")
    monkeypatch.setenv("EVENTS_DB", db_path)
    from hub.app import app
    with TestClient(app) as c:
        yield c


# --- Feature 1: kill-chain correlation --------------------------------------

def _alert(source, action, src_ip, ts, detail=None):
    return Event(
        source=source, service="ssh", action=action, src_ip=src_ip,
        detail=detail or {}, ts=ts, classification=ALERT, severity="high",
    )


def test_build_kill_chains_groups_orders_and_tags():
    events = [
        # attacker A (out of order on input) -- cowrie login then command
        _alert("cowrie", "command", "1.1.1.1", "2026-08-10T10:05:00", {"cmd": "ls"}),
        _alert("cowrie", "login", "1.1.1.1", "2026-08-10T10:00:00"),
        # attacker B -- samba discovery then canary trip
        _alert("samba", "list_dir", "2.2.2.2", "2026-08-10T11:00:00"),
        _alert("canarytoken", "token_trigger", "2.2.2.2", "2026-08-10T11:10:00"),
        # a benign event that must be ignored
        Event(source="persona", service="smb", action="open_file",
              src_ip="10.0.0.5", ts=MONDAY_10AM, classification=BENIGN, severity=INFO),
    ]

    chains = build_kill_chains(events)
    assert len(chains) == 2

    by_ip = {c["src_ip"]: c for c in chains}

    a = by_ip["1.1.1.1"]
    assert [s["action"] for s in a["steps"]] == ["login", "command"]
    assert a["steps"][0]["tactic"] == "Initial Access"
    assert a["steps"][0]["technique"] == "T1078 Valid Accounts"
    assert a["steps"][1]["tactic"] == "Execution"
    assert a["dwell_seconds"] == 300.0
    assert a["first_seen"] == "2026-08-10T10:00:00"
    assert a["last_seen"] == "2026-08-10T10:05:00"

    b = by_ip["2.2.2.2"]
    assert [s["action"] for s in b["steps"]] == ["list_dir", "token_trigger"]
    assert b["steps"][0]["tactic"] == "Discovery"
    assert b["steps"][0]["technique"] == "T1135 Network Share Discovery"
    assert b["steps"][1]["tactic"] == "Exfiltration"
    assert b["dwell_seconds"] == 600.0

    # sorted by most recent activity: B (11:10) before A (10:05)
    assert chains[0]["src_ip"] == "2.2.2.2"


def test_tag_fallback():
    ev = Event(source="mail", service="smtp", action="send_mail", src_ip="9.9.9.9")
    assert tag(ev) == ("Unknown", "-")


def test_api_killchains_endpoint(client):
    client.post("/events", json={
        "source": "cowrie", "service": "ssh", "action": "login",
        "src_ip": "198.51.100.9", "detail": {}, "raw": "",
        "ts": "2026-08-10T11:00:00",
    })
    client.post("/events", json={
        "source": "cowrie", "service": "ssh", "action": "command",
        "src_ip": "198.51.100.9", "detail": {"cmd": "id"}, "raw": "",
        "ts": "2026-08-10T11:05:00",
    })

    resp = client.get("/api/killchains")
    assert resp.status_code == 200
    chains = resp.json()
    assert len(chains) == 1
    chain = chains[0]
    assert chain["src_ip"] == "198.51.100.9"
    assert [s["action"] for s in chain["steps"]] == ["login", "command"]
    assert chain["dwell_seconds"] == 300.0


# --- Feature 2: canary HTTP callback ----------------------------------------

def test_canary_callback_returns_gif_and_stores_critical_alert(client, tmp_path):
    resp = client.get("/canary/it/passwords.xlsx", headers={"user-agent": "TestViewer/1.0"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/gif"
    assert resp.content.startswith(b"GIF89a")

    # Verify via a direct schema query on the tmp DB.
    import os
    db_path = os.environ["EVENTS_DB"]
    conn = connect(db_path)
    try:
        events = query_events(conn, classification=ALERT, limit=100)
    finally:
        conn.close()

    canary = next(e for e in events if e.source == "canarytoken")
    assert canary.action == "token_trigger"
    assert canary.service == "http"
    assert canary.severity == CRITICAL
    assert canary.classification == ALERT
    assert canary.dst_host == "canary-callback"
    assert canary.detail["token_id"] == "it/passwords.xlsx"
    assert canary.detail["user_agent"] == "TestViewer/1.0"


# --- Feature 3: outbound alerting -------------------------------------------

def test_notify_webhook_fires_on_critical(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK", "http://soc.example/hook")
    monkeypatch.delenv("ALERT_SYSLOG", raising=False)

    captured = []

    def fake_urlopen(req, timeout=None):
        captured.append(req)
        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b""
        return _Resp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    ev = Event(
        source="canarytoken", service="http", action="token_trigger",
        src_ip="6.6.6.6", detail={"token_id": "secret.xlsx"},
        classification=ALERT, severity=CRITICAL,
    )
    notify(ev)

    assert len(captured) == 1
    req = captured[0]
    assert req.full_url == "http://soc.example/hook"
    assert req.get_method() == "POST"
    body = json.loads(req.data.decode("utf-8"))
    assert body["source"] == "canarytoken"
    assert body["action"] == "token_trigger"
    assert body["src_ip"] == "6.6.6.6"
    assert body["severity"] == CRITICAL
    assert body["detail"] == {"token_id": "secret.xlsx"}


def test_notify_no_fire_on_benign(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK", "http://soc.example/hook")
    monkeypatch.delenv("ALERT_SYSLOG", raising=False)

    captured = []

    def fake_urlopen(req, timeout=None):
        captured.append(req)
        raise AssertionError("should not be called for benign/info events")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    benign = Event(source="persona", service="smb", action="open_file",
                   src_ip="10.0.0.5", classification=BENIGN, severity=INFO)
    notify(benign)

    info_alert = Event(source="samba", service="smb", action="list_dir",
                       src_ip="7.7.7.7", classification=ALERT, severity=INFO)
    notify(info_alert)

    assert captured == []


def test_notify_slack_payload(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK", "https://hooks.slack.com/services/T/B/X")
    monkeypatch.delenv("ALERT_SYSLOG", raising=False)

    captured = []

    def fake_urlopen(req, timeout=None):
        captured.append(req)
        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _Resp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    ev = Event(source="cowrie", service="ssh", action="login", src_ip="8.8.8.8",
               classification=ALERT, severity="high")
    notify(ev)

    assert len(captured) == 1
    body = json.loads(captured[0].data.decode("utf-8"))
    assert "text" in body
    assert "cowrie/login" in body["text"]
