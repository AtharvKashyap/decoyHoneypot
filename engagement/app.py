"""The tarpit service: an adaptive attacker-engagement web front end.

Every request an intruder makes against the fake "intranet" is:

  1. turned into a request context,
  2. answered with believable, synthetic fake content from `engine.respond`,
  3. logged to the hub as an event (source="intranet", action="browse") so a
     non-persona IP hitting it becomes an alert and its dwell time grows,
  4. optionally slowed by a small, capped, configurable delay to physically
     waste the attacker's time,
  5. returned as HTML or plain text.

Importable as `engagement.app:app`. The event sink is chosen by `core.events`:
HUB_URL set -> POST to the hub; unset -> write to the local SQLite store (tests).
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from core.events import get_sink
from core.schema import Event
from engagement import engine

app = FastAPI(title="Meridian Logistics Internal Portal")

# Max delay we will ever sleep, so a misconfiguration can't hang the service.
_MAX_DELAY_MS = 10_000

_LANDING = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Meridian Logistics -- Internal Portal</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:Segoe UI,Arial,sans-serif;background:#0f1b2d;color:#e8eef7;
      margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center}
 .card{background:#16243a;padding:2.5rem 2.75rem;border-radius:10px;
       box-shadow:0 8px 30px rgba(0,0,0,.4);width:340px}
 h1{font-size:1.15rem;margin:0 0 .25rem} .sub{color:#8aa0bd;font-size:.85rem;margin-bottom:1.5rem}
 label{display:block;font-size:.8rem;color:#a9bcd6;margin:.75rem 0 .25rem}
 input{width:100%;box-sizing:border-box;padding:.55rem .65rem;border:1px solid #2c3f5c;
       border-radius:6px;background:#0f1b2d;color:#e8eef7}
 button{margin-top:1.25rem;width:100%;padding:.6rem;border:0;border-radius:6px;
        background:#2f6fed;color:#fff;font-weight:600;cursor:pointer}
 .foot{margin-top:1.25rem;font-size:.72rem;color:#5f76a0;text-align:center}
</style></head>
<body>
 <form class="card" method="post" action="/portal/login">
   <h1>Meridian Logistics</h1>
   <div class="sub">Employee Intranet -- authorized use only</div>
   <label for="u">Username</label>
   <input id="u" name="username" autocomplete="username" placeholder="corp\\username">
   <label for="p">Password</label>
   <input id="p" name="password" type="password" autocomplete="current-password">
   <button type="submit">Sign in</button>
   <div class="foot">Helpdesk x4400 &middot; VPN: vpn.meridian-logistics.local</div>
 </form>
</body></html>"""


def _delay_ms() -> int:
    """Configured tarpit delay in ms, clamped to [0, _MAX_DELAY_MS]. Default 0."""
    try:
        ms = int(os.environ.get("TARPIT_DELAY_MS", "0"))
    except (TypeError, ValueError):
        return 0
    return max(0, min(ms, _MAX_DELAY_MS))


def _client_ip(request: Request) -> str:
    # Honor a proxy hop if present (the lab may front this), else the peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


@app.get("/", response_class=HTMLResponse)
def landing() -> HTMLResponse:
    """A believable internal-portal login page."""
    return HTMLResponse(content=_LANDING)


@app.api_route("/{full_path:path}", methods=["GET", "POST"])
def tarpit(full_path: str, request: Request):
    """Catch-all: serve adaptive fake content and log the engagement."""
    path = "/" + full_path
    context = {
        "path": path,
        "method": request.method,
        "service": "http",
        "client_ip": _client_ip(request),
        "query": dict(request.query_params),
    }

    body = engine.respond(context)

    # Emit the engagement to the hub (or local store when HUB_URL is unset).
    sink = get_sink()
    try:
        sink.emit(Event(
            source="intranet",
            service="http",
            action="browse",
            src_ip=context["client_ip"],
            dst_host="intranet-portal",
            detail={"path": path, "lure": "ai-generated", "engaged": True},
            classification="unknown",
        ))
    finally:
        sink.close()

    # Physically slow the attacker if configured (0 in tests).
    delay = _delay_ms()
    if delay:
        time.sleep(delay / 1000.0)

    lowered = body.lstrip().lower()
    if lowered.startswith("<!doctype") or lowered.startswith("<html"):
        return HTMLResponse(content=body)
    return PlainTextResponse(content=body)
