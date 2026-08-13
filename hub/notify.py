"""Alerting integrations: push high-signal alerts outward to a SOC.

Every sink is best-effort: `notify()` must never raise and never meaningfully
block ingest. Sinks are opt-in via environment variables, so with nothing
configured `notify()` is a no-op.

Sinks:
  * Webhook (env ALERT_WEBHOOK): POST compact JSON. If the URL points at Slack
    (contains "hooks.slack.com") send a Slack-style {"text": ...} payload.
  * Syslog (env ALERT_SYSLOG): "host:port" for UDP syslog, or "local" for the
    local syslog socket. Emits a one-line summary.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

from core.schema import ALERT, CRITICAL, HIGH, Event

_TIMEOUT = 2.0


def _summary(event: Event) -> str:
    """A one-line human summary of an alert."""
    return (
        f"[{event.severity.upper()}] {event.source}/{event.action} "
        f"from {event.src_ip or '?'} -> {event.dst_host or '?'} @ {event.ts}"
    )


def _payload(event: Event) -> dict:
    return {
        "ts": event.ts,
        "source": event.source,
        "action": event.action,
        "src_ip": event.src_ip,
        "severity": event.severity,
        "detail": event.detail,
    }


def _send_webhook(url: str, event: Event) -> None:
    if "hooks.slack.com" in url:
        body = {"text": _summary(event)}
    else:
        body = _payload(event)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=_TIMEOUT)
    except Exception:
        # best-effort: never let a webhook failure disrupt ingest.
        pass


def _send_syslog(target: str, event: Event) -> None:
    import logging.handlers
    import socket

    try:
        if target == "local":
            # Prefer the common local syslog socket; fall back to UDP localhost.
            address = "/dev/log"
            if not os.path.exists(address):
                address = ("localhost", 514)  # type: ignore[assignment]
            handler = logging.handlers.SysLogHandler(address=address)
        else:
            host, _, port = target.partition(":")
            handler = logging.handlers.SysLogHandler(
                address=(host, int(port) if port else 514),
                socktype=socket.SOCK_DGRAM,
            )
        logger = logging.getLogger("deception-grid.alert")
        logger.setLevel(logging.WARNING)
        logger.addHandler(handler)
        try:
            logger.warning(_summary(event))
        finally:
            handler.close()
            logger.removeHandler(handler)
    except Exception:
        # best-effort: syslog misconfig must not disrupt ingest.
        pass


def notify(event: Event) -> None:
    """Dispatch a high-signal alert to all configured sinks. Best-effort;
    never raises. No-op unless the event is a HIGH/CRITICAL ALERT."""
    try:
        if event.classification != ALERT or event.severity not in (HIGH, CRITICAL):
            return

        webhook = os.environ.get("ALERT_WEBHOOK")
        if webhook:
            _send_webhook(webhook, event)

        syslog = os.environ.get("ALERT_SYSLOG")
        if syslog:
            _send_syslog(syslog, event)
    except Exception:
        # absolute backstop -- notification must never break ingest.
        pass
