"""Tests for the adaptive attacker-engagement tarpit.

All offline (no ANTHROPIC_API_KEY): the engine is deterministic per path, and
the app logs each engagement to the local SQLite store when HUB_URL is unset.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.schema import connect, query_events
from engagement import engine


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch):
    # Force the deterministic offline path and the local-SQLite sink.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HUB_URL", raising=False)
    monkeypatch.setenv("TARPIT_DELAY_MS", "0")


# --- engine.respond routing --------------------------------------------------

def test_passwd_path_returns_passwd_like_content():
    body = engine.respond({"path": "/etc/passwd", "method": "GET",
                           "service": "http", "client_ip": "203.0.113.9"})
    assert "root:x:0:0:" in body
    assert body.count(":") > 10  # colon-delimited passwd rows


def test_config_path_returns_config_with_fake_creds():
    body = engine.respond({"path": "/secret/config.env", "method": "GET",
                           "service": "http", "client_ip": "203.0.113.9"})
    assert "DB_PASSWORD=" in body
    assert "SECRET_KEY=" in body
    assert "API_KEY" in body.upper()


def test_db_path_returns_sql_dump():
    body = engine.respond({"path": "/backups/db_backup.sql", "method": "GET",
                           "service": "http", "client_ip": "203.0.113.9"})
    assert "INSERT INTO" in body
    assert "CREATE TABLE" in body


def test_directory_path_returns_listing_with_breadcrumbs():
    body = engine.respond({"path": "/internal/files/", "method": "GET",
                           "service": "http", "client_ip": "203.0.113.9"})
    assert "Index of" in body
    assert "<a href=" in body  # tempting deeper links


def test_generic_path_returns_html():
    body = engine.respond({"path": "/wiki/onboarding", "method": "GET",
                           "service": "http", "client_ip": "203.0.113.9"})
    assert body.lstrip().lower().startswith("<!doctype")
    assert "</html>" in body.lower()


def test_offline_is_deterministic():
    ctx = {"path": "/srv/app/settings.py", "method": "GET",
           "service": "http", "client_ip": "203.0.113.9"}
    assert engine.respond(dict(ctx)) == engine.respond(dict(ctx))


def test_content_contains_no_unsynthesized_real_secret():
    # Sanity: everything is fabricated. Fake AWS keys use the AKIA prefix and
    # our own hex helper -- there is no real 40-char base64 secret smuggled in.
    body = engine.respond({"path": "/app/config.env", "method": "GET",
                           "service": "http", "client_ip": "203.0.113.9"})
    # Fabricated markers we deliberately synthesized are present...
    assert "sk-ant-fake-" in body
    # ...and no placeholder for a real, operator-supplied secret leaked through.
    assert "BEGIN RSA PRIVATE KEY" not in body


# --- app: engagement logging -------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "events.db")
    monkeypatch.setenv("EVENTS_DB", db_path)
    from engagement.app import app
    with TestClient(app) as c:
        c._db_path = db_path  # stash for assertions
        yield c


def test_get_fake_file_returns_200_and_emits_one_event(client):
    resp = client.get("/secret/config.env")
    assert resp.status_code == 200
    assert resp.text  # non-empty fake body

    conn = connect(client._db_path)
    events = query_events(conn)
    conn.close()

    assert len(events) == 1
    ev = events[0]
    assert ev.source == "intranet"
    assert ev.service == "http"
    assert ev.action == "browse"
    assert ev.detail["lure"] == "ai-generated"
    assert ev.detail["path"] == "/secret/config.env"
    assert ev.detail["engaged"] is True


def test_landing_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Meridian Logistics" in resp.text
