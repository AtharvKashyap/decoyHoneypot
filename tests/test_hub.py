"""Tests for the Hub: ingest, detection, dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.config import load_company
from core.schema import ALERT, BENIGN, UNKNOWN, connect, insert_event, Event
from hub.detection import classify, classify_store

# A Monday (2026-08-10 is a Monday) at 10:00 -- inside every example persona's
# work window (all Mon-Fri, 08:45-18:00-ish).
MONDAY_10AM = "2026-08-10T10:00:00"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "events.db")
    monkeypatch.setenv("EVENTS_DB", db_path)
    with TestClient_app() as c:
        yield c


def TestClient_app():
    # Imported lazily so EVENTS_DB env var (set by the fixture) is read fresh
    # per-request by hub.ingest.get_conn(), not baked in at import time.
    from hub.app import app
    return TestClient(app)


def test_persona_event_within_home_ip_and_hours_is_benign(client):
    resp = client.post("/events", json={
        "source": "persona", "service": "smb", "action": "open_file",
        "src_ip": "10.13.0.21", "dst_host": "fileserver", "identity": "jchen",
        "detail": {}, "raw": "", "ts": MONDAY_10AM,
    })
    assert resp.status_code == 200
    rid = resp.json()["id"]

    events = client.get("/api/events").json()
    match = next(e for e in events if e["id"] == rid)
    assert match["classification"] == BENIGN


def test_persona_event_wrong_src_ip_is_alert(client):
    resp = client.post("/events", json={
        "source": "persona", "service": "smb", "action": "open_file",
        "src_ip": "203.0.113.55", "dst_host": "fileserver", "identity": "jchen",
        "detail": {}, "raw": "", "ts": MONDAY_10AM,
    })
    assert resp.status_code == 200
    rid = resp.json()["id"]

    events = client.get("/api/events").json()
    match = next(e for e in events if e["id"] == rid)
    assert match["classification"] == ALERT


def test_cowrie_login_is_alert_high(client):
    resp = client.post("/events", json={
        "source": "cowrie", "service": "ssh", "action": "login",
        "src_ip": "198.51.100.9", "dst_host": "cowrie-ssh", "identity": None,
        "detail": {"username": "root", "password": "toor"}, "raw": "",
        "ts": MONDAY_10AM,
    })
    assert resp.status_code == 200
    rid = resp.json()["id"]

    events = client.get("/api/events").json()
    match = next(e for e in events if e["id"] == rid)
    assert match["classification"] == ALERT
    assert match["severity"] == "high"


def test_canarytoken_trigger_is_alert_critical(client):
    resp = client.post("/canary", json={
        "src_ip": "198.51.100.9", "canary_id": "it/passwords.xlsx",
        "service": "file",
    })
    assert resp.status_code == 200
    rid = resp.json()["id"]

    events = client.get("/api/events").json()
    match = next(e for e in events if e["id"] == rid)
    assert match["classification"] == ALERT
    assert match["severity"] == "critical"
    assert match["source"] == "canarytoken"
    assert match["action"] == "token_trigger"


def test_api_stats_counts_and_time_wasted(client):
    # Two benign persona events.
    client.post("/events", json={
        "source": "persona", "service": "smb", "action": "open_file",
        "src_ip": "10.13.0.21", "identity": "jchen", "detail": {}, "raw": "",
        "ts": MONDAY_10AM,
    })
    client.post("/events", json={
        "source": "persona", "service": "http", "action": "browse",
        "src_ip": "10.13.0.22", "identity": "rpatel", "detail": {}, "raw": "",
        "ts": MONDAY_10AM,
    })
    # Two alert (cowrie) events from the same attacker IP, 300s apart.
    client.post("/events", json={
        "source": "cowrie", "service": "ssh", "action": "login",
        "src_ip": "198.51.100.9", "detail": {}, "raw": "",
        "ts": "2026-08-10T11:00:00",
    })
    client.post("/events", json={
        "source": "cowrie", "service": "ssh", "action": "command",
        "src_ip": "198.51.100.9", "detail": {"cmd": "ls"}, "raw": "",
        "ts": "2026-08-10T11:05:00",
    })

    stats = client.get("/api/stats").json()
    assert stats["benign_count"] == 2
    assert stats["alert_count"] == 2
    assert stats["attacker_ip_count"] == 1
    assert isinstance(stats["time_wasted_seconds"], (int, float))
    assert stats["time_wasted_seconds"] == 300.0


def test_dashboard_root_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Deception Grid" in resp.text


def test_classify_store_updates_unknown_events(tmp_path):
    db_path = str(tmp_path / "seed.db")
    conn = connect(db_path)
    insert_event(conn, Event(
        source="persona", service="smb", action="open_file",
        src_ip="10.13.0.21", identity="jchen", ts=MONDAY_10AM,
    ))
    insert_event(conn, Event(
        source="cowrie", service="ssh", action="login",
        src_ip="1.2.3.4", ts=MONDAY_10AM,
    ))
    insert_event(conn, Event(
        source="canarytoken", service="file", action="token_trigger",
        src_ip="1.2.3.4", ts=MONDAY_10AM,
    ))
    conn.close()

    company = load_company("config/company.example.yaml")
    updated = classify_store(db_path, company)
    assert updated == 3

    conn = connect(db_path)
    rows = conn.execute("SELECT source, classification, severity FROM events ORDER BY id").fetchall()
    conn.close()

    by_source = {r["source"]: (r["classification"], r["severity"]) for r in rows}
    assert by_source["persona"] == (BENIGN, "info")
    assert by_source["cowrie"] == (ALERT, "high")
    assert by_source["canarytoken"] == (ALERT, "critical")
