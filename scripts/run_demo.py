#!/usr/bin/env python3
"""Offline end-to-end demo of the AI Deception Grid — no Docker, no API key.

Pipeline:
    1. generate       fabricate the fake company + seed docs (offline fallback)
    2. simulate day   personas produce a full day of benign activity
    3. attack         an intruder runs a kill-chain against the decoys
    4. detect         the detection engine classifies every event
    5. report         print the resulting benign/alert picture

Everything writes to a single fresh SQLite store, exactly like the real lab —
only here producers write directly instead of POSTing to the hub. Run the
dashboard afterwards (`make dash`) to view the same data.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

# Run from repo root regardless of invocation dir.
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

DB = os.environ.setdefault("EVENTS_DB", "data/events.db")
PY = str(ROOT / ".venv" / "bin" / "python")


def banner(step: str, msg: str) -> None:
    print(f"\n\033[1;36m[{step}]\033[0m {msg}")


def most_recent_weekday(d: date) -> date:
    """Nearest date on/before d that is Mon-Fri (personas don't work weekends)."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def main() -> int:
    # Fresh store so the demo is reproducible.
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = Path(DB + suffix)
        if p.exists():
            p.unlink()

    # 1. Generate the fake company + seed documents (offline fallback if no key).
    banner("1/5 generate", "fabricating the fake company + seed documents")
    subprocess.run([PY, "-m", "generator.generate"], check=True, cwd=ROOT)

    # Imports must come AFTER generation so config/company.yaml exists.
    from core.config import load_company
    from core.events import DirectSink
    from core.schema import query_events, BENIGN, ALERT
    from personas.engine import simulate_day
    from hub.detection import classify_store

    sys.path.insert(0, str(ROOT / "scripts"))
    from attacker_sim import run_attack  # scripts/attacker_sim.py

    company = load_company()
    sink = DirectSink(DB)

    # 2. A full day of simulated-employee activity (a recent weekday).
    day = most_recent_weekday(date.today())
    banner("2/5 personas", f"simulating employee activity for {day} (a weekday)")
    n_benign = simulate_day(company=company, date=day, sink=sink)
    print(f"    emitted {n_benign} benign persona events")

    # 3. The attacker.
    banner("3/5 attack", "intruder runs recon -> SMB exfil -> canary trip -> SSH honeypot")
    n_attack = run_attack(sink=sink, company=company)
    print(f"    emitted {n_attack} attacker events")
    sink.close()

    # 4. Detection classifies everything still 'unknown'.
    banner("4/5 detect", "classifying events against the persona baseline")
    updated = classify_store(DB, company)
    print(f"    classified {updated} events")

    # 5. Report.
    banner("5/5 report", "results")
    conn = __import__("core.schema", fromlist=["connect"]).connect(DB)
    benign = query_events(conn, classification=BENIGN, limit=100000)
    alerts = query_events(conn, classification=ALERT, limit=100000)
    print(f"    benign events : {len(benign)}")
    print(f"    ALERT events  : {len(alerts)}")
    attacker_ips = sorted({e.src_ip for e in alerts if e.src_ip})
    print(f"    attacker IPs  : {', '.join(attacker_ips) or '(none)'}")
    print(f"    alert sources : {', '.join(sorted({e.source for e in alerts}))}")

    misclassified = [e for e in benign if e.source != "persona"]
    assert not misclassified, f"benign set contains non-persona events: {misclassified}"
    assert alerts, "expected attacker activity to raise alerts"
    assert benign, "expected persona activity to form a benign baseline"

    print("\n\033[1;32mOK\033[0m  benign baseline is clean; attacker activity flagged.")
    print("     View it: make dash   ->   http://localhost:8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
