# AI Deception Grid

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
| `traps/`       | Honeypots & decoy services                                      | Cowrie, OpenCanary, Samba, MailHog |
| `core/`        | Shared event schema + config contract                          | stdlib + PyYAML     |

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
# ... open http://localhost:8000, then run the attacker demo:
python scripts/attacker_sim.py
make lab-down
```

## Containment

- The `deception` Docker network is `internal: true` — **no egress**. Decoys and
  traps cannot reach the internet or pivot outward.
- Only the hub publishes a port (the dashboard). Nothing else is exposed.
- Everything is synthetic: no real credentials, no real data.

## Layout

See `docs/superpowers/specs/2026-08-12-ai-deception-grid-design.md` for the full design.
