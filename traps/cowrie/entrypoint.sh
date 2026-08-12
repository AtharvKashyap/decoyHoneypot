#!/bin/sh
# Start the log forwarder sidecar in the background, then hand off to
# Cowrie's own entrypoint/foreground process so the container's PID 1 stays
# Cowrie (keeps `docker stop`/health checks behaving normally).
set -e

python3 /opt/forward.py &

# Delegate to the base image's normal startup.
exec /usr/local/bin/docker-entrypoint.sh cowrie start -n
