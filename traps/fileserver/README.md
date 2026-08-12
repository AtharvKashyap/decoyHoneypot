# fileserver (Samba)

Serves the `seed` volume (fabricated, partly-canaried documents produced by
the Decoy Generator) at `/share` over SMB with anonymous/guest read access —
matching a real, slightly-too-open small-business fileserver. Personas read
and edit files here as part of normal simulated activity; an attacker who
reaches the `deception` network can discover and pull the same tree.

## Real-time SMB read auditing (lab enhancement, not implemented here)

A production-grade version of this trap would run `smbd` with full-audit VFS
logging (or `auditd`) so every `open`/`read` on a canaried document emits a
`samba` event (`action="open_file"` / `"download"`) the instant an attacker
touches it — the same shape of event this build's `scripts/attacker_sim.py`
emits offline. Wiring that up (VFS audit module config + a log-tailing
sidecar following the `traps/forwarder.py` pattern used by `cowrie` and
`opencanary`) is straightforward but was left out of this container to keep
the image minimal; the offline attacker simulation demonstrates the exact
SMB-discovery-and-exfil event sequence a real intrusion would produce.

## Containment

This container only joins the `deception` network (see `docker-compose.yml`),
which is `internal: true` — no egress to the internet. Nothing here is real
company data; every document is synthetic, generated for this authorized
defensive research lab.
