# Cowrie SSH/Telnet honeypot with a forwarding sidecar that streams every
# session (login attempts + interactive commands) to the hub's event store.
#
# NOTE on forwarder.py: docker-compose.yml builds this image with context
# `./traps/cowrie` (scoped per service, not editable here), so the Dockerfile
# cannot COPY files from outside that directory. `forwarder.py` in this
# directory is therefore a same-content copy of the shared
# `traps/forwarder.py` helper -- see traps/README.md for details. Keep the two
# in sync if you change one.
FROM cowrie/cowrie:latest

USER root

COPY forwarder.py /opt/forwarder.py
COPY forward.py /opt/forward.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh /opt/forward.py

ENV HUB_URL=http://hub:8000
ENV COWRIE_LOG=/cowrie/cowrie-git/var/log/cowrie/cowrie.json

USER cowrie
ENTRYPOINT ["/opt/entrypoint.sh"]
