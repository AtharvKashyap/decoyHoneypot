"""The content brain for the adaptive attacker-engagement tarpit.

`respond(context)` returns a believable, entirely synthetic fake response body
for whatever an intruder is poking at on the fake "intranet". The whole point is
to *waste an attacker's time*: every artifact looks like a juicy internal-IT
secret (configs, credentials, DB dumps, directory trees) but is fabricated, and
every artifact seeds fresh breadcrumbs (more fake paths / hostnames / tokens) to
lure them deeper into an endless maze.

Two generators:

  * If ANTHROPIC_API_KEY is set, an Anthropic-backed generator produces the
    content (model/limits imported from config.model, never hardcoded). Any
    error at all falls back to the offline generator.
  * Otherwise a *deterministic* offline generator seeded from a hash of the
    requested path -- so the same request always yields byte-identical output
    (stable tests, and a consistent illusion for a returning attacker).

Nothing here is ever a real secret: all credentials, keys and hostnames are
freshly fabricated from fixed word pools.
"""

from __future__ import annotations

import hashlib
import os
import random
from typing import Any

from config.model import MAX_TOKENS, MODEL

# --- fabrication vocabularies ------------------------------------------------
# Fixed, obviously-internal-flavored pools. Combined by a seeded RNG so output
# is deterministic per path but varied across paths.

_HOSTS = [
    "mer-dc01", "mer-app02", "mer-sql03", "vault-prod", "jenkins-ci",
    "backup-nas1", "mer-fs04", "gitlab-int", "grafana01", "kube-master",
    "smtp-relay", "mer-vpn1", "ldap-primary", "redis-cache2", "es-node3",
]
_DOMAIN = "corp.meridian-logistics.local"
_USERS = [
    "svc_deploy", "jchen", "backup_admin", "svc_backup", "rgomez",
    "svc_sql", "dba_oncall", "helpdesk", "svc_scanner", "tmurray",
    "svc_ci", "netops", "svc_ldap", "pmehta", "root",
]
_SERVICES = [
    "payroll-api", "orders-svc", "billing-worker", "wms-core",
    "auth-gateway", "reporting-etl", "fleet-tracker", "invoice-render",
]
_TABLES = ["users", "sessions", "api_tokens", "invoices", "employees", "audit_log"]


def _rng(context: dict) -> random.Random:
    """Deterministic RNG seeded from the request path.

    Using only the path (not IP/method) keeps a given URL's fake artifact stable
    across visits, reinforcing the illusion and making tests reproducible.
    """
    path = str(context.get("path", ""))
    seed = int(hashlib.sha256(path.encode("utf-8")).hexdigest(), 16)
    return random.Random(seed)


def _token(rng: random.Random, n: int = 32) -> str:
    alphabet = "0123456789abcdef"
    return "".join(rng.choice(alphabet) for _ in range(n))


def _password(rng: random.Random) -> str:
    words = ["Winter", "Meridian", "Falcon", "Q3", "Logistics", "Vault",
             "Prod", "Titan", "Orbit", "Nimbus"]
    return f"{rng.choice(words)}{rng.choice(words)}{rng.randint(10, 99)}!"


def _pick(rng: random.Random, pool: list, n: int) -> list:
    n = min(n, len(pool))
    return rng.sample(pool, n)


# --- offline artifact generators ---------------------------------------------

def _gen_passwd(context: dict, rng: random.Random) -> str:
    """A believable /etc/passwd-style listing with fake service accounts."""
    lines = [
        "root:x:0:0:root:/root:/bin/bash",
        "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin",
        "bin:x:2:2:bin:/bin:/usr/sbin/nologin",
        "sys:x:3:3:sys:/dev:/usr/sbin/nologin",
        "sync:x:4:65534:sync:/bin:/bin/sync",
        "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin",
        "sshd:x:110:65534::/run/sshd:/usr/sbin/nologin",
    ]
    uid = 1000
    for user in _pick(rng, _USERS, 6):
        home = f"/home/{user}" if not user.startswith("svc_") else f"/opt/{user}"
        shell = "/bin/bash" if not user.startswith("svc_") else "/usr/sbin/nologin"
        lines.append(f"{user}:x:{uid}:{uid}:{user}:{home}:{shell}")
        uid += 1
    # Breadcrumb: a fake shadow reference in a comment nudges them onward.
    host = rng.choice(_HOSTS)
    lines.append(f"# synced from {host}.{_DOMAIN} -- see /etc/shadow.bak")
    return "\n".join(lines) + "\n"


def _gen_config(context: dict, rng: random.Random) -> str:
    """A fake application config studded with fabricated creds and API keys."""
    svc = rng.choice(_SERVICES)
    db_host = rng.choice(_HOSTS)
    db_user = rng.choice([u for u in _USERS if u.startswith("svc_")] or _USERS)
    cache_host = rng.choice(_HOSTS)
    return "\n".join([
        f"# {svc} -- environment configuration (generated)",
        "APP_ENV=production",
        f"APP_HOST={svc}.{_DOMAIN}",
        "",
        f"DB_HOST={db_host}.{_DOMAIN}",
        "DB_PORT=5432",
        f"DB_NAME={svc.replace('-', '_')}",
        f"DB_USER={db_user}",
        f"DB_PASSWORD={_password(rng)}",
        "",
        f"REDIS_URL=redis://{cache_host}.{_DOMAIN}:6379/0",
        f"SECRET_KEY={_token(rng, 48)}",
        f"JWT_SIGNING_KEY={_token(rng, 40)}",
        f"AWS_ACCESS_KEY_ID=AKIA{_token(rng, 16).upper()}",
        f"AWS_SECRET_ACCESS_KEY={_token(rng, 40)}",
        f"ANTHROPIC_API_KEY=sk-ant-fake-{_token(rng, 24)}",
        "",
        "# TODO: rotate before Q4 audit -- creds also in /srv/deploy/.env.bak",
        f"# vault: https://vault-prod.{_DOMAIN}/v1/secret/{svc}",
    ]) + "\n"


def _gen_dbdump(context: dict, rng: random.Random) -> str:
    """A fake SQL dump snippet with fabricated rows."""
    table = rng.choice(_TABLES)
    lines = [
        "-- MySQL dump 10.13  Distrib 8.0.36",
        f"-- Host: {rng.choice(_HOSTS)}.{_DOMAIN}    Database: meridian_prod",
        "-- ------------------------------------------------------",
        "",
        f"DROP TABLE IF EXISTS `{table}`;",
        f"CREATE TABLE `{table}` (",
        "  `id` int NOT NULL AUTO_INCREMENT,",
        "  `username` varchar(64) NOT NULL,",
        "  `email` varchar(128) NOT NULL,",
        "  `password_hash` varchar(120) NOT NULL,",
        "  `api_token` varchar(64) DEFAULT NULL,",
        "  PRIMARY KEY (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
        "",
        f"LOCK TABLES `{table}` WRITE;",
        f"INSERT INTO `{table}` VALUES",
    ]
    rows = []
    for i, user in enumerate(_pick(rng, _USERS, 6), start=1):
        pw_hash = "$2b$12$" + _token(rng, 22)
        rows.append(
            f"({i},'{user}','{user}@meridian-logistics.com',"
            f"'{pw_hash}','{_token(rng, 32)}')"
        )
    lines.append(",\n".join(rows) + ";")
    lines.append("UNLOCK TABLES;")
    lines.append(f"-- full backup at smb://backup-nas1.{_DOMAIN}/dumps/nightly/")
    return "\n".join(lines) + "\n"


def _gen_listing(context: dict, rng: random.Random) -> str:
    """A fake directory listing whose entries point deeper -- an endless maze."""
    path = str(context.get("path", "/")).rstrip("/") or ""
    # Tempting sub-entries: each links a deeper fake path so the crawl never ends.
    dirs = _pick(rng, [
        "backups", "credentials", "db_dumps", "configs", "keys", "payroll",
        "vpn", "archive", "old_site", "financials", "hr", "deploy",
    ], 5)
    files = _pick(rng, [
        "config.env", "passwd.bak", "db_backup.sql", "id_rsa", "wp-config.php",
        "settings.py", "credentials.csv", "vault_token.txt", ".env.production",
        "shadow.bak", "aws_keys.json", "root_password.txt",
    ], 6)
    rows = ['<pre>',
            f'<a href="../">../</a>']
    for d in dirs:
        rows.append(
            f'<a href="{path}/{d}/">{d}/</a>'
            f'{" " * (40 - len(d))}{rng.randint(2024, 2026)}-'
            f'{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}   -'
        )
    for f in files:
        size = rng.randint(512, 4_000_000)
        rows.append(
            f'<a href="{path}/{f}">{f}</a>'
            f'{" " * (40 - len(f))}{rng.randint(2024, 2026)}-'
            f'{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}   {size}'
        )
    rows.append('</pre>')
    body = "\n".join(rows)
    return (
        f"<!doctype html><html><head><title>Index of {path or '/'}</title></head>"
        f"<body><h1>Index of {path or '/'}</h1>\n{body}\n"
        f"<address>Apache/2.4.57 (Debian) Server at "
        f"{rng.choice(_HOSTS)}.{_DOMAIN} Port 80</address></body></html>"
    )


def _gen_wiki(context: dict, rng: random.Random) -> str:
    """A believable internal wiki / admin HTML page seeded with breadcrumbs."""
    path = str(context.get("path", "/"))
    svc = rng.choice(_SERVICES)
    hosts = _pick(rng, _HOSTS, 3)
    runbook_token = _token(rng, 12)
    return (
        "<!doctype html><html><head>"
        f"<title>Meridian IT Wiki -- {svc}</title></head><body>"
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:820px;'
        'margin:2rem auto">'
        '<nav style="color:#667">Home / Infrastructure / Runbooks</nav>'
        f"<h1>{svc} Runbook</h1>"
        f"<p>Internal service <code>{svc}.{_DOMAIN}</code>. On-call rotation in "
        'PagerDuty. Escalate to the Platform team.</p>'
        "<h2>Hosts</h2><ul>"
        + "".join(f"<li><code>{h}.{_DOMAIN}</code></li>" for h in hosts)
        + "</ul>"
        "<h2>Access</h2>"
        f"<p>Deploy user <code>svc_deploy</code>. Secrets live in "
        f'<a href="/srv/deploy/config.env">/srv/deploy/config.env</a> and the '
        f'<a href="/vault/secret/{svc}">vault path</a>. Nightly DB '
        f'<a href="/backups/db_backup.sql">dump here</a>.</p>'
        f"<h2>Recent changes</h2><ul>"
        f'<li><a href="/wiki/admin/">Admin console</a></li>'
        f'<li><a href="/internal/passwd.bak">host account export</a></li>'
        f'<li>Runbook rev token: <code>{runbook_token}</code></li>'
        "</ul>"
        f'<footer style="color:#889;margin-top:2rem;font-size:.85em">'
        f"Requested: {path} -- Meridian Logistics confidential</footer>"
        "</div></body></html>"
    )


# Route table: (substrings to match in the path) -> generator.
def _route(context: dict) -> Any:
    path = str(context.get("path", "")).lower()

    def has(*needles: str) -> bool:
        return any(n in path for n in needles)

    if has("passwd", "shadow"):
        return _gen_passwd
    if has("config", ".env", "settings"):
        return _gen_config
    if has("db", "dump", "backup", ".sql"):
        return _gen_dbdump
    # Directory-ish: trailing slash, or no filename-with-extension segment.
    last = path.rstrip("/").rsplit("/", 1)[-1]
    looks_like_dir = path.endswith("/") or ("." not in last)
    if looks_like_dir and path not in ("", "/"):
        return _gen_listing
    if has("wiki", "admin", "intranet", "portal") or path in ("", "/"):
        return _gen_wiki
    return _gen_wiki


def offline_respond(context: dict) -> str:
    """Deterministic, fully offline fake content for a request context."""
    rng = _rng(context)
    return _route(context)(context, rng)


# --- optional Anthropic-backed generator -------------------------------------

_SYSTEM = (
    "You are generating fake internal-IT artifacts for an AUTHORIZED defensive "
    "honeypot (a tarpit). Everything you produce must be entirely FABRICATED and "
    "contain NO real secrets -- invent plausible-looking hostnames, usernames, "
    "passwords, API keys and data. The artifact should look like a tempting "
    "internal file an intruder would want to read, and should reference a few "
    "additional fake internal paths/hostnames as breadcrumbs. Keep it to about a "
    "screenful. Output ONLY the artifact content, no commentary."
)


def _ai_respond(context: dict) -> str:
    """Anthropic-backed generation; raises on any problem so caller can fall back."""
    import anthropic  # lazy: offline path needs no SDK

    client = anthropic.Anthropic()
    path = str(context.get("path", "/"))
    method = str(context.get("method", "GET"))
    service = str(context.get("service", "http"))
    prompt = (
        f"An intruder on our decoy network sent a {method} request to path "
        f"'{path}' over {service}. Produce a single believable but completely "
        "fake internal-IT artifact appropriate to that path (e.g. a unix passwd "
        "file, an app config with fake creds/API keys, a SQL dump snippet, a "
        "directory listing, or an internal wiki/admin page). All values must be "
        "invented. Include a couple of tempting fake breadcrumbs (extra paths, "
        "hostnames, or tokens)."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    if getattr(resp, "stop_reason", None) == "refusal":
        raise RuntimeError("model declined the request")
    text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("empty completion")
    return text


def respond(context: dict) -> str:
    """Return a believable, synthetic fake response body for a request context.

    Uses the Anthropic SDK when ANTHROPIC_API_KEY is present, falling back to the
    deterministic offline generator on ANY error. Without the key, the offline
    generator is used directly (deterministic per path).
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _ai_respond(context)
        except Exception:
            return offline_respond(context)
    return offline_respond(context)
