"""Behaviour / persona engine — simulated employees living a 9-5 workday.

This is the deception grid's baseline generator. Each `Persona` from
`config/company.yaml` gets a plausible day: they log in a few minutes either
side of their start time, open/edit/close/share files on their own SMB share,
browse the intranet, send internal mail, ssh to the jumphost, take a lunch
break, and log out around their end time. Nothing happens outside the work
window or on a non-work day — that silence is precisely what makes off-hours
activity detectable.

Two ways to drive it:

  * `simulate_day()` — plan and emit an entire workday instantly. Used by the
    offline demo and the tests.
  * `run()`          — the container entrypoint: an asyncio loop that emits the
    planned events in (scaled) real time, honouring `TIME_SCALE`, optionally
    performing real network I/O against the lab's decoy services.

Determinism: every plan is produced from an RNG seeded by
(seed, persona.username, date), so the same inputs always yield the same day.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import time
from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone
from typing import Iterable, Optional

from core.config import Company, Persona, WorkHours, load_company
from core.events import get_sink
from personas.actions import perform

try:  # zoneinfo is stdlib on 3.9+, but tz databases can be missing on slim images
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

# --- Tuning knobs -----------------------------------------------------------
LOGIN_JITTER_MIN = 6            # log in 0..6 min after the nominal start
LOGOUT_JITTER_MIN = 8           # log out 1..8 min before the nominal end
LUNCH_MIN_MINUTES = 35          # lunch gap length
LUNCH_MAX_MINUTES = 55
LUNCH_SHIFT_MIN = 20            # how far lunch drifts around the day's midpoint
BURSTS_PER_WEIGHT_HOUR = 1 / 6  # activity bursts = total_weight * hours * this
MIN_BURSTS = 2
GAP_MIN_SECONDS = 20            # spacing inside a file-handling burst
GAP_MAX_SECONDS = 240

# Activities a persona config may weight. `close_file` is never weighted: it is
# generated as the natural tail of an open/edit burst.
WEIGHTED_ACTIONS = ("open_file", "edit_file", "share_file", "browse", "send_mail", "ssh")


# --- Time helpers -----------------------------------------------------------

def _parse_hhmm(value: str | time_cls) -> time_cls:
    """Parse an 'HH:MM' (or 'HH:MM:SS') work-hours string into a `time`."""
    if isinstance(value, time_cls):
        return value
    parts = [int(p) for p in str(value).strip().split(":")]
    while len(parts) < 3:
        parts.append(0)
    return time_cls(parts[0], parts[1], parts[2])


def _tzinfo(work_hours: WorkHours):
    name = getattr(work_hours, "tz", None) or "UTC"
    if name.upper() == "UTC" or ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - unknown tz name: fall back to UTC
        return timezone.utc


def _as_date(value: Optional[date_cls | datetime]) -> date_cls:
    if value is None:
        return datetime.now(timezone.utc).date()
    if isinstance(value, datetime):
        return value.date()
    return value


def work_window(persona: Persona, day: date_cls) -> tuple[datetime, datetime]:
    """The persona's (start, end) datetimes on `day`, in their own timezone.

    An end time earlier than the start (an overnight shift) rolls to the next
    calendar day so the window is always non-empty.
    """
    wh = persona.work_hours
    tz = _tzinfo(wh)
    start = datetime.combine(day, _parse_hhmm(wh.start), tzinfo=tz)
    end = datetime.combine(day, _parse_hhmm(wh.end), tzinfo=tz)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def is_working(persona: Persona, dt: datetime) -> bool:
    """True iff `dt` falls inside this persona's work window on a work day.

    `dt` may be naive (assumed UTC) or aware; it is converted into the
    persona's own timezone before the day/window checks.
    """
    tz = _tzinfo(persona.work_hours)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(tz)

    days = list(persona.work_hours.days or [])
    # An overnight window that started "yesterday" still counts as yesterday's shift.
    for day_offset in (0, -1):
        day = (local + timedelta(days=day_offset)).date()
        if day.weekday() not in days:
            continue
        start, end = work_window(persona, day)
        if start <= local < end:
            return True
    return False


# --- Planning ---------------------------------------------------------------

def _rng_for(persona: Persona, day: date_cls, seed: int) -> random.Random:
    """A stable RNG for (seed, persona, date).

    Uses a hash digest rather than `hash()` because Python salts string hashing
    per process, which would make plans differ between runs.
    """
    key = f"{seed}|{persona.username}|{day.isoformat()}".encode()
    digest = hashlib.sha256(key).digest()[:8]
    return random.Random(int.from_bytes(digest, "big"))


def _burst_for(action: str, rng: random.Random) -> list[str]:
    """Expand one chosen activity into a realistic little sequence of actions."""
    if action == "open_file":
        seq = ["open_file"]
        if rng.random() < 0.4:
            seq.append("edit_file")
        seq.append("close_file")
        return seq
    if action == "edit_file":
        return ["open_file", "edit_file", "close_file"]
    return [action]


def _sample_in_segments(
    rng: random.Random, segments: list[tuple[datetime, datetime]], count: int
) -> list[datetime]:
    """Pick `count` timestamps spread across the given (start, end) segments,
    weighted by each segment's length, returned sorted."""
    spans = [max(0.0, (e - s).total_seconds()) for s, e in segments]
    total = sum(spans)
    if total <= 0 or count <= 0:
        return []
    picks: list[datetime] = []
    for _ in range(count):
        offset = rng.uniform(0, total)
        for (seg_start, _seg_end), span in zip(segments, spans):
            if offset <= span:
                picks.append(seg_start + timedelta(seconds=offset))
                break
            offset -= span
    return sorted(picks)


def plan_day(
    persona: Persona,
    date: Optional[date_cls | datetime] = None,
    seed: int = 0,
) -> list[tuple[datetime, str]]:
    """Build one persona's ordered (timestamp, action) plan for `date`.

    Returns `[]` on a non-work day. Every timestamp is inside the persona's work
    window (so `is_working()` is True for all of them), with a lunch gap around
    midday. The number and mix of activities is driven by
    `persona.activity_weights`; the result is deterministic for a given
    (seed, persona, date).
    """
    day = _as_date(date)
    if day.weekday() not in list(persona.work_hours.days or []):
        return []

    rng = _rng_for(persona, day, seed)
    start, end = work_window(persona, day)

    login_at = start + timedelta(seconds=rng.randint(0, LOGIN_JITTER_MIN * 60))
    logout_at = end - timedelta(seconds=rng.randint(60, LOGOUT_JITTER_MIN * 60))
    if logout_at <= login_at:  # pathologically short window: login/logout only
        return [(login_at, "login"), (max(login_at, end - timedelta(seconds=1)), "logout")]

    # Lunch gap: drifts around the midpoint of the working window.
    midpoint = login_at + (logout_at - login_at) / 2
    lunch_start = midpoint + timedelta(seconds=rng.randint(-LUNCH_SHIFT_MIN * 60, LUNCH_SHIFT_MIN * 60))
    lunch_end = lunch_start + timedelta(minutes=rng.randint(LUNCH_MIN_MINUTES, LUNCH_MAX_MINUTES))

    work_start = login_at + timedelta(seconds=60)
    work_end = logout_at - timedelta(seconds=60)
    segments: list[tuple[datetime, datetime]] = []
    if lunch_start > work_start and lunch_end < work_end:
        segments = [(work_start, lunch_start), (lunch_end, work_end)]
    else:  # lunch fell outside the usable range; one continuous block
        segments = [(work_start, work_end)]
    segments = [(s, e) for s, e in segments if e > s]

    weights = {
        a: float(w) for a, w in (persona.activity_weights or {}).items()
        if a in WEIGHTED_ACTIONS and float(w) > 0
    }
    if not weights:  # a persona with no weights still shows up and browses
        weights = {"browse": 1.0}

    hours = (logout_at - login_at).total_seconds() / 3600.0
    total_weight = sum(weights.values())
    n_bursts = max(MIN_BURSTS, round(total_weight * hours * BURSTS_PER_WEIGHT_HOUR))

    action_names = sorted(weights)
    action_weights = [weights[a] for a in action_names]
    starts = _sample_in_segments(rng, segments, n_bursts)

    planned: list[tuple[datetime, str]] = [(login_at, "login")]
    for burst_start, segment in zip(starts, _segment_of(starts, segments)):
        chosen = rng.choices(action_names, weights=action_weights, k=1)[0]
        cursor = burst_start
        for step in _burst_for(chosen, rng):
            if cursor >= segment[1]:  # keep the burst inside its own segment
                break
            planned.append((cursor, step))
            cursor += timedelta(seconds=rng.randint(GAP_MIN_SECONDS, GAP_MAX_SECONDS))
    planned.append((logout_at, "logout"))

    planned.sort(key=lambda item: item[0])
    # Belt-and-braces: never emit anything outside the work window.
    return [(ts, action) for ts, action in planned if start <= ts < end]


def _segment_of(
    timestamps: list[datetime], segments: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """For each timestamp, the segment it landed in (used to bound its burst)."""
    out = []
    for ts in timestamps:
        match = next((seg for seg in segments if seg[0] <= ts <= seg[1]), segments[-1])
        out.append(match)
    return out


# --- Emission ---------------------------------------------------------------

def plan_company_day(
    company: Company, day: date_cls, seed: int = 0
) -> list[tuple[datetime, Persona, str]]:
    """Every persona's plan for `day`, merged into one chronological timeline."""
    merged: list[tuple[datetime, Persona, str]] = []
    for persona in company.personas:
        for ts, action in plan_day(persona, day, seed=seed):
            merged.append((ts, persona, action))
    merged.sort(key=lambda item: item[0])
    return merged


def simulate_day(
    company: Optional[Company] = None,
    date: Optional[date_cls | datetime] = None,
    sink=None,
    seed: int = 0,
    live: bool = False,
) -> int:
    """Plan and emit a full workday for every persona at once.

    Returns the number of events emitted. Loads the company config and an event
    sink from the environment when not supplied (offline default: SQLite).
    """
    company = company or load_company()
    owns_sink = sink is None
    sink = sink or get_sink()
    day = _as_date(date)
    count = 0
    try:
        for ts, persona, action in plan_company_day(company, day, seed=seed):
            rng = _rng_for(persona, day, seed ^ count)
            perform(action, persona, sink, live=live, ts=ts, rng=rng)
            count += 1
    finally:
        if owns_sink:
            sink.close()
    return count


# --- Real-time (scaled) loop ------------------------------------------------

def _live_enabled() -> bool:
    """Whether to attempt real protocol I/O. Defaults on inside the lab (where
    HUB_URL points at the hub container), off for local dry-runs."""
    raw = os.environ.get("PERSONA_LIVE")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(os.environ.get("HUB_URL"))


def _time_scale() -> float:
    try:
        scale = float(os.environ.get("TIME_SCALE", "1.0"))
    except ValueError:
        scale = 1.0
    return scale if scale > 0 else 1.0


async def run_async(
    company: Optional[Company] = None,
    sink=None,
    seed: int = 0,
    max_days: Optional[int] = None,
) -> int:
    """Emit persona activity in scaled real time until cancelled.

    A virtual clock advances `TIME_SCALE`x faster than the wall clock; each
    planned event fires when the virtual clock reaches its timestamp, so the
    engine naturally goes quiet at night and on weekends.
    """
    company = company or load_company()
    owns_sink = sink is None
    sink = sink or get_sink()
    live = _live_enabled()
    scale = _time_scale()

    epoch_virtual = datetime.now(timezone.utc)
    epoch_real = time.monotonic()

    def virtual_now() -> datetime:
        return epoch_virtual + timedelta(seconds=(time.monotonic() - epoch_real) * scale)

    print(f"[personas] engine up: {len(company.personas)} personas, "
          f"TIME_SCALE={scale}, live_io={live}", flush=True)

    emitted = 0
    days_done = 0
    day = virtual_now().date()
    try:
        while max_days is None or days_done < max_days:
            timeline = [
                item for item in plan_company_day(company, day, seed=seed)
                if item[0] > virtual_now()
            ]
            for ts, persona, action in timeline:
                delay = (ts - virtual_now()).total_seconds() / scale
                while delay > 0:
                    await asyncio.sleep(min(delay, 5.0))
                    delay = (ts - virtual_now()).total_seconds() / scale
                rng = _rng_for(persona, day, seed ^ emitted)
                perform(action, persona, sink, live=live, ts=virtual_now(), rng=rng)
                emitted += 1
            days_done += 1
            day = day + timedelta(days=1)
            # Idle until the virtual clock reaches the next day (nights/weekends
            # are deliberately silent).
            next_midnight = datetime.combine(day, time_cls(0, 0), tzinfo=timezone.utc)
            gap = (next_midnight - virtual_now()).total_seconds() / scale
            while gap > 0:
                await asyncio.sleep(min(gap, 5.0))
                gap = (next_midnight - virtual_now()).total_seconds() / scale
    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        pass
    finally:
        if owns_sink:
            sink.close()
    print(f"[personas] engine down after {emitted} events", flush=True)
    return emitted


def run(**kwargs) -> int:
    """Blocking entrypoint for the container (`python -m personas.run`)."""
    try:
        return asyncio.run(run_async(**kwargs))
    except KeyboardInterrupt:  # pragma: no cover - operator Ctrl-C
        print("[personas] interrupted", flush=True)
        return 0


def iter_actions(plan: Iterable[tuple[datetime, str]]) -> list[str]:
    """Small helper for tests/debugging: just the action names from a plan."""
    return [action for _ts, action in plan]
