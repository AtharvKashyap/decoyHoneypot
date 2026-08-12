# Generic trap log-forwarder sidecar.
#
# Runs alongside a honeypot container, tails its log from a shared volume, and
# POSTs each attacker interaction to the hub as a core.schema.Event. Kept as a
# separate image so honeypots (e.g. the upstream cowrie/cowrie image, which has
# no shell) stay completely unmodified.
#
# Build context is ./traps so it can pull in the shared helper plus each trap's
# record-mapping script.
FROM python:3.11-slim
WORKDIR /app

COPY forwarder.py /app/forwarder.py
COPY cowrie/forward.py /app/cowrie_forward.py

# Default target is cowrie; docker-compose overrides `command` per sidecar.
CMD ["python", "/app/cowrie_forward.py"]
