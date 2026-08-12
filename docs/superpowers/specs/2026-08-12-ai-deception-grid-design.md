# Project: AI-Driven Deception Grid (Decoys + Honeypots + Simulated Users)

## Context

We're building a **deception-technology lab**: a network full of believable decoy systems and
honeypots that (a) waste and slow down attackers, (b) detect intrusions with near-zero false
positives, and (c) look *alive and lived-in* thanks to AI-driven simulated employees who "work"
9–5, open/close/edit/share files, browse the intranet, and send mail.

The novel value vs. off-the-shelf deception tools (Thinkst Canary, T-Pot, Cymmetria) is the
**behavior-simulation engine**: most honeypots are conspicuously *empty and static*, which tips off
skilled attackers. By generating realistic human activity and AI-authored content, our decoys read
as real production systems — making them far stickier traps.

**v1 target:** a self-contained **Docker-Compose lab on one host** that demonstrates the complete
loop end-to-end. Leverage existing OSS honeypots; build the AI/orchestration layer on top.

### The core detection insight
Simulated employees ("personas") authenticate with **known decoy accounts from known source IPs on
a known schedule**. That defines a tight *benign baseline*. Therefore:
> Any interaction that is **not** a scheduled persona action — and **every** touch of a pure
> honeypot or canary token — is an intruder. This yields high-signal, low-false-positive alerts.

## Goals (v1)
- One-command spin-up/reset of the whole deception lab (`docker compose up`).
- A believable fake org: AI-generated employee personas, hostnames, and document content.
- Trap layer from proven OSS: SSH honeypot, multi-service tripwires, canary-token files.
- **Behavior engine**: personas generate scheduled benign activity (9–5 with jitter, weekends off,
  open/edit/close/share files, browse intranet, send mail).
- Central event collector + **detection** that separates persona-benign from attacker activity.
- **Attacker slowdown**: tarpits, artificial latency, deep/endless fake filesystems, large lure files.
- A simple web **dashboard**: live timeline, benign baseline vs. alerts, attacker session replay,
  and a "attacker time wasted" metric.
- **Containment**: decoys are network-isolated with no outbound internet and no real credentials.

## Non-goals (v1 — deferred to stretch)
- Cloud/VPC deployment, multi-host orchestration.
- Full ELK/Kibana stack (we use a lightweight store + dashboard instead).
- ML-based anomaly detection (baseline rules are enough and more explainable).
- Live LLM-driven adaptive attacker engagement (designed for, but gated behind a flag).

## Architecture

### Topology (all containers on one isolated Docker bridge network)
```
                    ┌─────────────────────────────────────────────┐
                    │            deception-net (isolated)          │
                    │                                              │
  Persona Engine ──►│  fileserver (Samba)   intranet (fake portal) │
  (benign actors)   │  mailhog (fake mail)  jumphost (real SSHD)   │◄── Attacker
                    │                                              │    (you, red-team)
                    │  --- pure traps (any touch = alert) ---      │
                    │  cowrie (SSH honeypot)                       │
                    │  opencanary (FTP/HTTP/MySQL/SMB tripwires)   │
                    │  canarytokens (decoy-file callbacks)         │
                    └───────────────┬──────────────────────────────┘
                                    │ logs / events (syslog, files, HTTP webhooks)
                                    ▼
                     Collector  →  SQLite event store  →  Detection engine
                                                              │
                                                              ▼
                                                     Dashboard (FastAPI + HTML)
```

### Components

**A. Existing OSS (the trap layer) — leveraged, not rebuilt**
- **Cowrie** — SSH/Telnet honeypot with a fake shell + filesystem; logs every attacker command.
  Pure trap: no persona ever logs in, so any session = attacker. Also provides tarpit delays.
- **OpenCanary** — lightweight multi-service tripwires (FTP, HTTP admin, MySQL, SMB, etc.). Any
  connection = high-confidence alert.
- **Canarytokens** (self-hosted or hosted) — generates decoy files (Office docs, fake AWS keys,
  URLs) that phone home when opened/exfiltrated. Seeded across the fileserver by the generator.
- **Samba / MailHog / a plain OpenSSH container** — realistic *usable* services the personas
  actually interact with, so the environment has genuine benign traffic (not just traps).

**B. Novel components (what we build)**
1. **Decoy Generator** (`generator/`) — uses Claude to fabricate a coherent fake company: employee
   personas (name, role, hours, home IP, credentials, file-access habits), hostnames, directory
   trees, and **document contents** (fake financials, HR files, "passwords.xlsx", meeting notes).
   Embeds canary tokens into a subset of documents. Emits: persona configs + seeded fileserver +
   OpenCanary/Cowrie config. Claude is called **once at build time** (cheap, deterministic seed).
2. **Behavior / Persona Engine** (`personas/`) — the star. An async scheduler (APScheduler) where
   each persona follows a daily routine with realistic jitter: clock in ~9am, open/edit/close/share
   files over SMB, browse the intranet (HTTP), send internal mail (SMTP→MailHog), SSH to the
   jumphost, lunch gap, clock out ~5pm, quiet nights/weekends, occasional benign anomalies. Every
   action is emitted to the collector tagged with the persona identity so it's provably benign.
3. **Collector + Event Store** (`collector/`) — ingests Cowrie JSON logs, OpenCanary alerts,
   canary-token webhooks, Samba audit logs, and persona-emitted events into a single **SQLite**
   event schema (ts, source, service, src_ip, identity, action, raw).
4. **Detection Engine** (`detection/`) — classifies each event: `benign` (matches a scheduled
   persona identity/IP/window), `alert` (any pure-trap/canary hit, or off-baseline activity on
   usable services), with severity. Explainable rules, no black box.
5. **Slowdown/Tarpit layer** — Cowrie's built-in delays + configurable latency, an "endless"
   fake directory generator, and oversized lure files. Tracks time-in-trap per attacker session.
6. **Dashboard** (`dashboard/`) — FastAPI + server-rendered HTML (no build step): live event
   timeline, benign-baseline vs. alerts, per-attacker session replay (Cowrie commands), canary
   trigger map, and the "attacker time wasted" counter.

## Tech stack
- **Python 3.12** (matches Cowrie/OpenCanary ecosystem; great for scheduling + Anthropic SDK).
- **Docker Compose** for the lab; each component a service on one isolated bridge network.
- **anthropic** SDK with **`claude-fable-5`** for build-time content generation (and the stretch
  adaptive-engagement path). Model id centralized in one config constant.
- **APScheduler / asyncio** for persona scheduling; **impacket/smbclient**, **requests**,
  **smtplib**, **paramiko** for persona actions.
- **SQLite** event store; **FastAPI + Jinja2** dashboard. No JS build tooling.
- **pytest** for unit tests (detection rules, schedule logic, generator output validation).

## Repository structure
```
decoyHoneypot/
├── docker-compose.yml           # the whole lab
├── .env.example                 # ANTHROPIC_API_KEY, network config (no real secrets)
├── config/
│   ├── company.yaml             # generated fake-org definition (personas, hosts)
│   └── model.py                 # MODEL = "claude-fable-5"
├── generator/                   # AI decoy + content generation (build-time)
├── personas/                    # behavior/persona engine (runtime daemon)
├── collector/                   # log ingestion → SQLite
├── detection/                   # benign-vs-attacker classification rules
├── dashboard/                   # FastAPI + HTML
├── traps/                       # cowrie/opencanary/canary/samba configs + seed data
├── tests/
└── docs/superpowers/specs/      # design doc lives here
```

## Implementation phases (milestones)
1. **Lab skeleton** — docker-compose with Cowrie + OpenCanary + Samba + intranet + collector +
   SQLite; one-command up/reset; verify each service reachable on the isolated net.
2. **Decoy Generator** — Claude-driven `company.yaml` + seeded fileserver docs + canary tokens;
   validate output schema with tests.
3. **Behavior Engine** — one persona doing a full scheduled day of SMB/HTTP/SMTP/SSH actions,
   emitting benign events; then scale to several personas with jitter and off-hours.
4. **Detection + Dashboard** — classify events; render timeline, baseline vs. alerts, session replay,
   time-wasted metric.
5. **Slowdown layer** — tarpit latency, endless dirs, lure files; measure attacker dwell time.
6. **Red-team demo & docs** — run a scripted attacker (nmap → find SMB → grab canary doc → SSH into
   Cowrie) and show the alerts + slowdown; write README + demo script.
7. **Stretch (flagged off):** live LLM adaptive engagement; ELK export; cloud deploy.

## Safety, containment & ethics (required)
Honeypots are dangerous if they can be turned against real assets or third parties. v1 enforces:
- **No outbound internet** from decoy containers (internal Docker network only; egress blocked).
- **No real credentials or data** anywhere — everything is synthetic and clearly fake to operators.
- **Isolation** from the host and any real LAN; decoys cannot pivot outward.
- **Defensive-use framing**: this is an authorized-lab / research tool. README states intended use
  (own network / authorized engagements only) and the containment guarantees.

## Verification / demo plan
- `docker compose up` brings the whole lab healthy; `make reset` returns to a clean state.
- Unit tests (`pytest`) pass for generator schema, schedule windows, and detection classification
  (benign persona events → `benign`; synthetic trap hits → `alert`).
- **End-to-end demo:** run the persona engine for a compressed "day" and confirm the dashboard shows
  a clean benign baseline. Then run the scripted attacker; confirm: OpenCanary/Cowrie/canary alerts
  fire, the dashboard flags them against the baseline, session replay shows attacker commands, and
  the time-wasted counter climbs. Confirm no persona action is ever misclassified as an attack.

## Open questions to confirm before/at kickoff
- Compress persona schedule to "sped-up time" for demos (e.g., 1 day = 5 min) vs. real wall-clock?
  (Recommend a `TIME_SCALE` knob, default sped-up for demos.)
- Self-host Canarytokens vs. use the hosted canarytokens.org? (Recommend self-host for full offline
  containment.)
