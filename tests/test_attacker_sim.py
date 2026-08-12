"""Tests for the attacker simulation (scripts/attacker_sim.py).

Verifies the emitted kill-chain covers all four trap phases, uses an
attacker IP that is clearly outside the persona subnet, and includes a
realistic interactive SSH session and a canary trip.
"""

from __future__ import annotations

import ipaddress

from core.events import DirectSink
from core.schema import query_events
from scripts.attacker_sim import DEFAULT_ATTACKER_IP, run_attack

PERSONA_SUBNET = ipaddress.ip_network("10.13.0.0/24")


def test_run_attack_emits_events(tmp_path):
    db_path = str(tmp_path / "events.db")
    sink = DirectSink(db_path)

    count = run_attack(sink=sink, attacker_ip=DEFAULT_ATTACKER_IP)
    assert count > 0

    events = query_events(sink._conn, limit=1000)
    assert len(events) == count

    sources_seen = {e.source for e in events}
    for expected in ("opencanary", "samba", "canarytoken", "cowrie"):
        assert expected in sources_seen, f"missing phase source: {expected}"

    sink.close()


def test_attacker_ip_outside_persona_subnet(tmp_path):
    db_path = str(tmp_path / "events.db")
    sink = DirectSink(db_path)

    run_attack(sink=sink, attacker_ip=DEFAULT_ATTACKER_IP)

    assert ipaddress.ip_address(DEFAULT_ATTACKER_IP) not in PERSONA_SUBNET

    events = query_events(sink._conn, limit=1000)
    for e in events:
        if e.src_ip:
            assert ipaddress.ip_address(e.src_ip) not in PERSONA_SUBNET

    sink.close()


def test_cowrie_session_has_multiple_commands(tmp_path):
    db_path = str(tmp_path / "events.db")
    sink = DirectSink(db_path)

    run_attack(sink=sink, attacker_ip=DEFAULT_ATTACKER_IP)

    events = query_events(sink._conn, limit=1000)
    cowrie_commands = [
        e for e in events if e.source == "cowrie" and e.action == "command"
    ]
    assert len(cowrie_commands) >= 3

    cowrie_logins = [e for e in events if e.source == "cowrie" and e.action == "login"]
    assert len(cowrie_logins) >= 1

    sink.close()


def test_canary_token_trigger_present(tmp_path):
    db_path = str(tmp_path / "events.db")
    sink = DirectSink(db_path)

    run_attack(sink=sink, attacker_ip=DEFAULT_ATTACKER_IP)

    events = query_events(sink._conn, limit=1000)
    triggers = [
        e for e in events
        if e.source == "canarytoken" and e.action == "token_trigger"
    ]
    assert len(triggers) == 1
    assert triggers[0].detail.get("token_id")

    sink.close()
