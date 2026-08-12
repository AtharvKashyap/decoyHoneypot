"""Tests for the behaviour / persona engine.

The persona baseline is what detection depends on, so these tests pin down the
two properties the hub relies on: personas are active *only* inside their work
window on work days, and their plans are reproducible.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.config import load_company
from core.events import DirectSink
from core.schema import query_events
from personas import actions
from personas.engine import is_working, plan_day, simulate_day

# 2026-08-10 is a Monday; 08-15/08-16 are Saturday/Sunday.
MONDAY = datetime(2026, 8, 10).date()
TUESDAY = datetime(2026, 8, 11).date()
SATURDAY = datetime(2026, 8, 15).date()
SUNDAY = datetime(2026, 8, 16).date()


@pytest.fixture(scope="module")
def company():
    return load_company("config/company.example.yaml")


@pytest.fixture(scope="module")
def slee(company):
    """Sophie Lee: a plain 09:00-17:00 Mon-Fri UTC persona."""
    return company.persona_by_username("slee")


def _utc(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


# --- is_working -------------------------------------------------------------

def test_is_working_inside_weekday_window(slee):
    assert is_working(slee, _utc(MONDAY, 9, 1))
    assert is_working(slee, _utc(MONDAY, 13, 30))
    assert is_working(slee, _utc(TUESDAY, 16, 59))


def test_is_working_false_outside_window(slee):
    assert not is_working(slee, _utc(MONDAY, 3, 0))     # 3am
    assert not is_working(slee, _utc(MONDAY, 8, 59))    # just before start
    assert not is_working(slee, _utc(MONDAY, 17, 0))    # end is exclusive
    assert not is_working(slee, _utc(MONDAY, 22, 0))


def test_is_working_false_at_weekend(slee):
    for hour in (3, 9, 13, 17, 23):
        assert not is_working(slee, _utc(SATURDAY, hour))
        assert not is_working(slee, _utc(SUNDAY, hour))


def test_is_working_respects_per_persona_hours(company):
    """rpatel works 09:30-18:00, so 09:00 is too early and 17:30 still counts."""
    rpatel = company.persona_by_username("rpatel")
    assert not is_working(rpatel, _utc(MONDAY, 9, 0))
    assert is_working(rpatel, _utc(MONDAY, 17, 30))


def test_is_working_accepts_naive_datetime(slee):
    assert is_working(slee, datetime(2026, 8, 10, 12, 0))
    assert not is_working(slee, datetime(2026, 8, 10, 4, 0))


# --- plan_day ---------------------------------------------------------------

def test_plan_day_all_inside_work_window(company):
    for persona in company.personas:
        plan = plan_day(persona, MONDAY, seed=7)
        assert plan, f"{persona.username} planned nothing on a work day"
        for ts, action in plan:
            assert is_working(persona, ts), f"{persona.username} {action} at {ts}"


def test_plan_day_is_chronological_and_bookended(company):
    for persona in company.personas:
        plan = plan_day(persona, MONDAY, seed=3)
        stamps = [ts for ts, _ in plan]
        assert stamps == sorted(stamps)
        assert plan[0][1] == "login"
        assert plan[-1][1] == "logout"


def test_plan_day_empty_at_weekend(company):
    for persona in company.personas:
        assert plan_day(persona, SATURDAY, seed=1) == []
        assert plan_day(persona, SUNDAY, seed=1) == []


def test_plan_day_has_a_lunch_gap(slee):
    """The largest gap between consecutive events should be a lunch-sized one
    somewhere around the middle of the day."""
    plan = plan_day(slee, MONDAY, seed=11)
    stamps = [ts for ts, _ in plan]
    gaps = [(b - a, a) for a, b in zip(stamps, stamps[1:])]
    biggest, gap_start = max(gaps, key=lambda g: g[0])
    assert biggest >= timedelta(minutes=30)
    assert 11 <= gap_start.hour <= 15


def test_plan_day_mix_follows_activity_weights(company):
    """jchen has ssh weight 0 and never sshes; rpatel (ssh 4) does."""
    jchen = company.persona_by_username("jchen")
    rpatel = company.persona_by_username("rpatel")
    jchen_actions = {a for _ts, a in plan_day(jchen, MONDAY, seed=5)}
    rpatel_actions = {a for _ts, a in plan_day(rpatel, MONDAY, seed=5)}
    assert "ssh" not in jchen_actions
    assert "ssh" in rpatel_actions
    assert "open_file" in jchen_actions


def test_plan_day_deterministic_for_same_seed_and_date(company):
    for persona in company.personas:
        first = plan_day(persona, MONDAY, seed=42)
        second = plan_day(persona, MONDAY, seed=42)
        assert first == second


def test_plan_day_varies_by_seed_and_date(slee):
    assert plan_day(slee, MONDAY, seed=1) != plan_day(slee, MONDAY, seed=2)
    assert plan_day(slee, MONDAY, seed=1) != plan_day(slee, TUESDAY, seed=1)


# --- actions ----------------------------------------------------------------

def test_build_event_shape(slee):
    ev = actions.build_event("open_file", slee)
    assert ev.source == "persona"
    assert ev.service == "smb"
    assert ev.identity == "slee"
    assert ev.src_ip == slee.home_ip
    assert ev.classification == "unknown"
    assert ev.detail["file"] in slee.files_owned


def test_build_event_service_per_action(slee):
    expected = {
        "open_file": "smb", "edit_file": "smb", "close_file": "smb",
        "share_file": "smb", "browse": "http", "send_mail": "smtp",
        "ssh": "ssh", "login": "ssh", "logout": "ssh",
    }
    for action, service in expected.items():
        assert actions.build_event(action, slee).service == service


def test_perform_never_raises_on_live_io_failure(slee, tmp_path):
    """Live I/O against absent lab services must still produce an event."""
    sink = DirectSink(str(tmp_path / "live.db"))
    ev = actions.perform("browse", slee, sink, live=True)
    assert ev.detail["live"] in ("ok", "failed")
    assert len(query_events(sink._conn)) == 1
    sink.close()


# --- simulate_day -----------------------------------------------------------

def test_simulate_day_emits_valid_persona_events(company, tmp_path):
    sink = DirectSink(str(tmp_path / "events.db"))
    count = simulate_day(company=company, date=MONDAY, sink=sink, seed=13)
    assert count > 0

    rows = query_events(sink._conn, limit=10000)
    assert len(rows) == count

    ips = {p.home_ip for p in company.personas}
    names = {p.username for p in company.personas}
    for ev in rows:
        assert ev.source == "persona"
        assert ev.identity in names
        assert ev.src_ip in ips
        assert company.persona_by_username(ev.identity).home_ip == ev.src_ip
        assert ev.classification == "unknown"
        persona = company.persona_by_username(ev.identity)
        ts = datetime.fromisoformat(ev.ts)
        assert is_working(persona, ts), f"{ev.identity} {ev.action} at {ev.ts}"
    sink.close()


def test_simulate_day_silent_at_weekend(company, tmp_path):
    sink = DirectSink(str(tmp_path / "weekend.db"))
    assert simulate_day(company=company, date=SATURDAY, sink=sink, seed=13) == 0
    assert query_events(sink._conn) == []
    sink.close()


def test_simulate_day_deterministic(company, tmp_path):
    def actions_for(db_name):
        sink = DirectSink(str(tmp_path / db_name))
        simulate_day(company=company, date=MONDAY, sink=sink, seed=99)
        rows = query_events(sink._conn, limit=10000)
        sink.close()
        return [(r.ts, r.identity, r.action, r.detail.get("file") or r.detail.get("url"))
                for r in rows]

    assert actions_for("a.db") == actions_for("b.db")
