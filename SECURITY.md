# Security & Responsible Use

The AI Deception Grid is **defensive** security tooling: it builds decoys and
honeypots to detect, study, and slow down intruders on a network you own or are
authorized to defend. It is intended for blue teams, security researchers, and
authorized red-team/purple-team engagements.

## Authorized use only

- Deploy it **only** on infrastructure you own or have **written authorization**
  to test. Running honeypots or attacker simulations against systems or networks
  you do not control may be illegal.
- The included attacker simulation (`scripts/attacker_sim.py`) and live red-team
  toolbox (`scripts/live_attack/`) are for exercising **your own** lab. Do not
  point them at third-party systems.

## Containment guarantees

- The lab's `deception` Docker network is `internal: true` — decoys and traps
  have **no route to the internet** and cannot phone home or pivot outward.
- Only the hub publishes a port (the operator dashboard). Nothing else is exposed.
- All content is **synthetic**: fabricated personas, fake documents, fake
  credentials. There are no real secrets or real user data anywhere in this repo,
  and you should never place real secrets into it.

## Operating it safely

- Keep it isolated from production networks and real identity providers.
- Treat any credentials an attacker "finds" as bait — they grant access to nothing.
- If you extend the traps, preserve the no-egress containment and the
  synthetic-only rule.

## Reporting a vulnerability

If you find a security issue in this project, please open a private report via
GitHub Security Advisories on the repository, or contact the maintainer directly,
rather than filing a public issue. Please do not include real secrets or
production data in any report.
