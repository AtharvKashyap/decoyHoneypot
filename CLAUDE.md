# CLAUDE.md — AI Deception Grid

Guidance for AI agents working in this repo. Keep it current as the design evolves.

## What this is

A single-host **deception lab**: AI-generated decoys + OSS honeypots, made believable
by an AI **behavior engine** that simulates employees living a 9–5 workday. Detection
works by treating simulated personas as a known-benign baseline; everything else is an
attacker. **Defensive/authorized-lab use only.**

## Golden rules

- **`core/` is the contract.** The event schema (`core/schema.py`), company config
  (`core/config.py`), and emission helper (`core/events.py`) are the interfaces every
  component shares. Change them deliberately; update all consumers.
- **Everything must run offline.** No API key and no Docker should be required to
  develop or test. The generator falls back to deterministic content; producers write
  straight to SQLite when `HUB_URL` is unset. `make demo` is the offline E2E.
- **Containment is non-negotiable.** The `deception` network is `internal: true`
  (no egress). No real secrets or data anywhere — it's all synthetic.
- **Model id lives in `config/model.py`** (`MODEL = "claude-fable-5"`). Never hardcode.

## Key contracts

- **Event** (`core/schema.py`): `source`, `service`, `action`, `src_ip`, `dst_host`,
  `identity`, `detail`, `classification` (`benign`/`alert`/`unknown`), `severity`.
  Producers emit via `core.events.get_sink()`.
- **Company** (`core/config.py`): personas (username, `home_ip`, `work_hours`,
  `files_owned`, `activity_weights`), hosts (`is_trap`), documents (`canary`).
  Loaded from `config/company.yaml`, falling back to `config/company.example.yaml`.
- **Detection baseline:** a persona event is benign iff its `identity`/`src_ip` matches
  a known persona within its work window. Trap sources (`cowrie`, `opencanary`,
  `canarytoken`) are always alerts.

## Commands

```bash
make install   # venv + deps
make test      # pytest
make demo      # offline end-to-end
make dash      # dashboard on :8000
make lab       # docker compose up
make lab-config# validate compose file
```

## Conventions

- Python 3.12+, standard library first; typed dataclasses over ORMs.
- Tests live in `tests/`, named `test_*.py`. Add tests with every component.
- Git commits: concise, imperative, **no author/co-author trailers**.

## Layout

`core/` shared contract · `generator/` AI decoy generation · `personas/` behavior
engine · `hub/` ingest+detection+dashboard · `traps/` honeypot configs ·
`scripts/` demo/attacker sim · `docs/superpowers/specs/` design doc.
