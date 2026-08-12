# AI Deception Grid

[![CI](https://github.com/OWNER/decoyHoneypot/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

An **AI-driven deception lab**: a network of believable decoys and honeypots that
waste attackers' time, detect intrusions with near-zero false positives, and — the
novel part — look *alive* thanks to AI-simulated employees who "work" 9–5, opening,
editing, and sharing files, browsing the intranet, and sending mail.

> **Authorized/defensive use only.** This is a research and blue-team lab meant to
> run on your own isolated network. See [Containment](#containment).

## Why it's different

Most honeypots are conspicuously empty and static, which tips off skilled attackers.
Here, **simulated personas** generate a realistic benign baseline. That baseline is
what powers detection:

> Personas act from **known accounts, known IPs, on a known schedule**. Anything
> outside that baseline — and *every* touch of a pure trap or canary token — is an
> intruder. High signal, near-zero false positives.

## Architecture

```
Persona Engine ─► decoys (fileserver / intranet / jumphost / mail)  ◄─ Attacker
                  pure traps (cowrie / opencanary / canary tokens)
                        │  events
                        ▼
        Collector ─► SQLite event store ─► Detection ─► Dashboard (:8000)
```

| Component      | Role                                                             | Built on            |
|----------------|-----------------------------------------------------------------|---------------------|
| `generator/`   | AI-generates the fake org + document contents (offline fallback)| Claude / templates  |
| `personas/`    | Behavior engine: simulated employees on a schedule              | APScheduler         |
| `hub/`         | Ingest + detection + dashboard                                  | FastAPI + SQLite    |
| `traps/`       | Honeypots & decoy services (+ log forwarders → hub)             | Cowrie, OpenCanary, Samba, Mailpit |
| `engagement/`  | AI tarpit: serves believable fake content to waste attacker time| Claude / templates  |
| `core/`        | Shared event schema + config contract                          | stdlib + PyYAML     |

Live detection covers all of it: the Cowrie SSH honeypot and OpenCanary tripwires
forward every hit; the Samba fileserver audits file reads so **exfiltration and
canary-token trips appear on the dashboard in real time**; and the AI tarpit logs
each time it lures an intruder deeper.

## Quick start (no Docker, no API key needed)

```bash
make install      # venv + deps
make test         # unit tests
make demo         # offline end-to-end: generate -> personas -> attacker -> detect
make dash         # view the dashboard at http://localhost:8000
```

## Full lab (Docker)

```bash
cp .env.example .env      # optionally add ANTHROPIC_API_KEY
make generate             # build the fake org + seed documents
make lab                  # docker compose up the whole deception grid
make attack               # run a REAL red-team kill-chain against the live lab
# open http://localhost:8000 to watch it land, then:
make lab-down
```

`make attack` builds a small red-team toolbox image (nmap, ssh, smbclient) and
runs it *on* the sealed deception network, executing a real kill-chain:
port-scan → SMB discovery/exfil of canaried docs → OpenCanary tripwire probes →
brute-force into the Cowrie SSH honeypot and run a recon session. The honeypots'
forwarders relay every interaction to the hub, where it lands as alerts against
the persona baseline. `personas` (auto-started by `make lab`) supplies the
benign 9–5 traffic, so the dashboard shows the same benign-vs-alert split as the
offline demo — but from live containers.

## Runs anywhere

- **App layer** (generate / personas / hub / detection / offline demo) is pure
  Python — Linux, macOS, and Windows, Python 3.11/3.12. CI runs the suite on all
  three OSes.
- **Container lab** uses multi-arch images only (Cowrie, Mailpit, Samba, Alpine,
  `python:slim`), so it runs natively on both `amd64` and `arm64` (Apple Silicon)
  with no emulation.
- CI (`.github/workflows/ci.yml`) additionally spins up the honeypot + hub in
  Docker, runs the live attacker, and asserts the alert reaches the hub.

## Containment

- The `deception` Docker network is `internal: true` — **no egress**. Decoys and
  traps cannot reach the internet or pivot outward.
- Only the hub publishes a port (the dashboard). Nothing else is exposed.
- Everything is synthetic: no real credentials, no real data.

## Layout

See `docs/superpowers/specs/2026-08-12-ai-deception-grid-design.md` for the full design.
