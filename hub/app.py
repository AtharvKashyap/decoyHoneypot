"""FastAPI Hub: ingest + detection + dashboard for the AI Deception Grid.

Run with:
    .venv/bin/uvicorn hub.app:app --port 8000

Endpoints:
    POST /events        -- ingest a raw Event (JSON, shape = Event.as_dict())
    POST /canary         -- canarytoken webhook (any JSON payload)
    GET  /api/stats      -- headline counts + "attacker time wasted" metric
    GET  /api/events     -- list events, optional ?classification=&limit=
    GET  /                -- server-rendered dashboard (auto-refreshing)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from core.schema import ALERT, BENIGN, Event, query_events
from hub.correlation import build_kill_chains
from hub.ingest import event_from_dict, get_conn, get_company, ingest_event

app = FastAPI(title="AI Deception Grid - Hub")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# A 1x1 transparent GIF returned by the canary HTTP callback so the fetching
# app (a document viewer opening an exfiltrated decoy) gets a valid image.
_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01"
    b"\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@app.post("/events")
async def post_event(request: Request) -> JSONResponse:
    payload = await request.json()
    event = event_from_dict(payload)
    conn = get_conn()
    try:
        rid = ingest_event(event, conn=conn, company=get_company())
    finally:
        conn.close()
    return JSONResponse({"id": rid})


@app.post("/canary")
async def post_canary(request: Request) -> JSONResponse:
    payload: dict[str, Any] = {}
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    event = Event(
        source="canarytoken",
        service=payload.get("service", "file"),
        action="token_trigger",
        src_ip=payload.get("src_ip", payload.get("source_ip", "")),
        dst_host=payload.get("dst_host", payload.get("canary_id", "")),
        identity=payload.get("identity"),
        detail=payload if isinstance(payload, dict) else {"raw": str(payload)},
        raw=str(payload),
    )
    conn = get_conn()
    try:
        rid = ingest_event(event, conn=conn, company=get_company())
    finally:
        conn.close()
    return JSONResponse({"id": rid})


@app.get("/canary/{token:path}")
async def canary_callback(token: str, request: Request) -> Response:
    """Real file-based canary HTTP callback: fires when an exfiltrated decoy
    document is opened in an app that fetches a remote resource. Records a
    CRITICAL canarytoken alert and returns a 1x1 transparent GIF."""
    src_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    event = Event(
        source="canarytoken",
        service="http",
        action="token_trigger",
        src_ip=src_ip,
        dst_host="canary-callback",
        detail={
            "token_id": token,
            "user_agent": user_agent,
            "note": "canary document opened off-network",
        },
        raw=str(request.url),
    )
    conn = get_conn()
    try:
        ingest_event(event, conn=conn, company=get_company())
    finally:
        conn.close()
    return Response(content=_PIXEL_GIF, media_type="image/gif")


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def compute_stats(conn) -> dict[str, Any]:
    all_events = query_events(conn, limit=10_000_000)
    counts: dict[str, int] = defaultdict(int)
    for ev in all_events:
        counts[ev.classification] += 1

    alert_events = [ev for ev in all_events if ev.classification == ALERT]
    attacker_ips = {ev.src_ip for ev in alert_events if ev.src_ip}

    per_ip_times: dict[str, list[datetime]] = defaultdict(list)
    for ev in alert_events:
        if not ev.src_ip:
            continue
        dt = _parse_ts(ev.ts)
        if dt is not None:
            per_ip_times[ev.src_ip].append(dt)

    time_wasted_seconds = 0.0
    for ip, times in per_ip_times.items():
        if len(times) < 2:
            continue
        span = (max(times) - min(times)).total_seconds()
        time_wasted_seconds += span

    return {
        "total_events": len(all_events),
        "counts": dict(counts),
        "benign_count": counts.get(BENIGN, 0),
        "alert_count": counts.get(ALERT, 0),
        "unknown_count": counts.get("unknown", 0),
        "attacker_ip_count": len(attacker_ips),
        "attacker_ips": sorted(attacker_ips),
        "time_wasted_seconds": time_wasted_seconds,
    }


@app.get("/api/stats")
def api_stats() -> JSONResponse:
    conn = get_conn()
    try:
        stats = compute_stats(conn)
    finally:
        conn.close()
    return JSONResponse(stats)


@app.get("/api/events")
def api_events(classification: Optional[str] = None, limit: int = Query(default=500, le=10000)) -> JSONResponse:
    conn = get_conn()
    try:
        events = query_events(conn, classification=classification, limit=limit)
    finally:
        conn.close()
    return JSONResponse([ev.as_dict() for ev in events])


@app.get("/api/killchains")
def api_killchains() -> JSONResponse:
    conn = get_conn()
    try:
        alert_events = query_events(conn, classification=ALERT, limit=10_000_000)
    finally:
        conn.close()
    return JSONResponse(build_kill_chains(alert_events))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    conn = get_conn()
    try:
        stats = compute_stats(conn)
        recent_events = query_events(conn, limit=50)
        alert_events = query_events(conn, classification=ALERT, limit=100)
        all_alerts = query_events(conn, classification=ALERT, limit=10_000_000)
        cowrie_events = [ev for ev in query_events(conn, limit=10_000_000) if ev.source == "cowrie"]
    finally:
        conn.close()

    kill_chains = build_kill_chains(all_alerts)

    sessions: dict[str, list[Event]] = defaultdict(list)
    for ev in cowrie_events:
        sessions[ev.src_ip or "unknown"].append(ev)
    for ip in sessions:
        sessions[ip].sort(key=lambda e: e.ts)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "recent_events": recent_events,
            "alert_events": alert_events,
            "sessions": dict(sessions),
            "kill_chains": kill_chains,
        },
    )
