# traps/

Trap layer for the **AI Deception Grid** — an authorized, isolated,
defensive honeypot lab (blue-team research). Everything under this
directory is synthetic decoy infrastructure: fake hosts, fake data, fake
credentials. Nothing here holds or exposes real company assets. This is
legitimate defensive tooling, built to detect and slow down attackers who
reach the deception network — not to attack anything.

## Containment model

`docker-compose.yml` (repo root, not modified by this layer) puts every trap
and decoy on the `deception` network, which is declared `internal: true`:
containers on it have **no route to the internet** and cannot phone home,
pivot outward, or be used to attack anything beyond this lab. Only the `hub`
service also joins the `frontend` network, solely to expose the operator
dashboard on `localhost:8000`. Everything else — cowrie, opencanary,
fileserver, intranet, jumphost — is sealed off from any external network and
reachable only from other containers on `deception`.

## The traps

### `cowrie/` — SSH/Telnet honeypot (pure trap)
Wraps the upstream `cowrie/cowrie` image with a `forward.py` sidecar that
tails Cowrie's JSON session log (`var/log/cowrie/cowrie.json`) and posts each
login attempt and shell command to the hub as `source="cowrie"` events
(`action="login"` / `"command"`). Any interaction here is, by construction,
an attacker: no persona ever legitimately touches this host.

### `opencanary/` — multi-service tripwire (pure trap)
A minimal `python:3.11-slim` build running OpenCanary with `ftp`, `http`,
`mysql`, and `smb` fake services enabled (see `opencanary.conf`). A
`forward.py` sidecar tails OpenCanary's JSON log and forwards every
probe/connection to the hub as `source="opencanary"`. Like cowrie, this host
has no legitimate traffic — a single packet here is a signal.

### `fileserver/` — the real, usable decoy Samba share
Serves the `seed` volume (fabricated, partly-canaried documents from the
Decoy Generator) at `/share` over SMB with anonymous/guest read access.
Personas read these files as part of normal simulated activity; an attacker
who reaches the `deception` network can discover and pull the same tree.
See `fileserver/README.md`: real-time SMB read auditing that would turn a
live file open/download into a `samba` event is noted there as a lab
enhancement — the offline `scripts/attacker_sim.py` demonstrates that exact
discovery → exfil → canary-trip sequence without needing it wired up live.

### `intranet/` — fake internal web portal
A ~30-line Flask app serving a believable "Meridian Logistics Intranet"
login page and landing page. Purely cosmetic: no credential submitted here
is validated, stored, or forwarded anywhere.

### `jumphost/` — plain SSH host (not a trap)
An OpenSSH server image (`linuxserver/openssh-server`) with a couple of
low-value local accounts (`jchen`, `rpatel`, `slee`) matching the persona
usernames in `config/company.example.yaml`, so simulated persona SSH
activity has a real host and real (synthetic) credentials to authenticate
against in the lab.

## Shared forwarding helper

`traps/forwarder.py` is the canonical implementation of two small helpers
used by every trap sidecar:

- `post_event(event_dict)` — POST an `Event`-shaped dict to `$HUB_URL/events`.
- `tail_json(path)` — a generator that follows a newline-delimited JSON log
  file, yielding each decoded record as it's appended (waits for the file to
  exist, skips malformed lines).

`docker-compose.yml` builds each trap with a **per-service build context**
(e.g. `build: ./traps/cowrie`), which is a repo-level file this layer does
not modify. Because a Docker build context can't reach files outside itself,
`cowrie/forward.py` and `opencanary/forward.py` cannot `COPY ../forwarder.py`
directly — so `cowrie/forwarder.py` and `opencanary/forwarder.py` are
same-content copies of the shared helper, checked in alongside each trap's
own `forward.py`. If you change the shared logic, update all three copies
together.

## Everything here is synthetic

Every document, credential, hostname, and IP address in this lab is
fabricated for research purposes. This trap layer is part of an authorized
defensive deception grid used to study attacker behavior in a fully isolated
environment — it is not deployed against, and has no path to, any real
system.
