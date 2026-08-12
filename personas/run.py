"""Entrypoint for the behaviour engine.

    .venv/bin/python -m personas.run          # long-running scaled-real-time loop
    RUN_ONCE=1 .venv/bin/python -m personas.run   # emit one full day and exit

Environment:
    TIME_SCALE    float; 1.0 = real time, higher = faster (default 1.0)
    RUN_ONCE      truthy -> simulate_day() once, then exit (smoke check / demo)
    SIM_DATE      YYYY-MM-DD; the day to simulate with RUN_ONCE (default: today)
    SIM_SEED      int; RNG seed for deterministic plans (default 0)
    PERSONA_LIVE  truthy -> attempt real SMB/HTTP/SMTP/SSH I/O (default: on when
                  HUB_URL is set, i.e. inside the lab)
    HUB_URL       set -> POST events to the hub; unset -> write to SQLite
    EVENTS_DB     SQLite path used when HUB_URL is unset
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime

from personas.engine import _live_enabled, run, simulate_day


def _truthy(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in ("1", "true", "yes", "on")


def _sim_date() -> date | None:
    raw = os.environ.get("SIM_DATE")
    if not raw:
        return None
    return datetime.strptime(raw.strip(), "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    run_once = _truthy(os.environ.get("RUN_ONCE")) or "--once" in argv
    seed = int(os.environ.get("SIM_SEED", "0"))

    if run_once:
        day = _sim_date()
        count = simulate_day(date=day, seed=seed, live=_live_enabled())
        print(f"[personas] simulated {day or 'today'}: {count} events emitted", flush=True)
        return 0

    run(seed=seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
