# A red-team toolbox image for driving a REAL attack against the live lab.
#
# Tools are baked in at build time (which has internet), so the container can
# then run attached to the sealed, no-egress `deception` network and still have
# everything it needs. Alpine keeps it small and multi-arch (runs natively on
# amd64 and arm64 — no emulation), matching the project's "works anywhere" goal.
FROM alpine:3.20
RUN apk add --no-cache openssh-client sshpass nmap samba-client netcat-openbsd curl bash
COPY attack.sh /attack.sh
RUN chmod +x /attack.sh
ENTRYPOINT ["/attack.sh"]
