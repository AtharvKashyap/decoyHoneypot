# Samba fileserver with file-access auditing.
#
# The real, usable decoy share: personas' documents live here (AI-generated,
# some canaried), and an attacker who pivots into the deception network can
# discover and pull them over SMB. Samba's full_audit VFS module logs every
# file OPEN to syslog; rsyslog writes those to a shared log file that the
# fileserver-forwarder sidecar tails and turns into hub events — so live
# exfiltration (and canary trips) show up on the dashboard in real time.
#
# Custom image (not dperson/samba) so we fully control the audit config, and
# built on debian:trixie-slim which is multi-arch (amd64 + arm64, no emulation).
FROM debian:trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends samba rsyslog \
    && rm -rf /var/lib/apt/lists/*

COPY smb.conf /etc/samba/smb.conf
COPY rsyslog-audit.conf /etc/rsyslog.d/30-samba-audit.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 139 445
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
