"""Smoke tests for the shared core contract."""

from core.schema import (
    Event, connect, insert_event, query_events, BENIGN, ALERT, HIGH,
)
from core.config import load_company
from core.events import DirectSink


def test_event_roundtrip(tmp_path):
    db = str(tmp_path / "e.db")
    conn = connect(db)
    ev = Event(source="persona", service="smb", action="open_file",
               src_ip="10.13.0.21", identity="jchen", classification=BENIGN)
    rid = insert_event(conn, ev)
    assert rid == 1
    rows = query_events(conn)
    assert len(rows) == 1
    assert rows[0].identity == "jchen"
    assert rows[0].classification == BENIGN


def test_query_filter_by_classification(tmp_path):
    conn = connect(str(tmp_path / "e.db"))
    insert_event(conn, Event(source="persona", service="http", action="browse",
                             classification=BENIGN))
    insert_event(conn, Event(source="cowrie", service="ssh", action="login",
                             classification=ALERT, severity=HIGH))
    assert len(query_events(conn, classification=ALERT)) == 1
    assert len(query_events(conn, classification=BENIGN)) == 1


def test_direct_sink(tmp_path):
    sink = DirectSink(str(tmp_path / "e.db"))
    sink.emit(Event(source="persona", service="smb", action="edit_file"))
    rows = query_events(sink._conn)
    assert len(rows) == 1
    sink.close()


def test_example_company_loads():
    c = load_company("config/company.example.yaml")
    assert c.name == "Meridian Logistics"
    assert len(c.personas) == 3
    assert c.persona_by_ip("10.13.0.21").username == "jchen"
    # traps flagged correctly
    trap_names = {h.name for h in c.trap_hosts()}
    assert "cowrie-ssh" in trap_names
    assert "canary-multi" in trap_names
