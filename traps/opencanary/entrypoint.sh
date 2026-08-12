#!/bin/sh
# Start the log forwarder sidecar, then run opencanaryd in the foreground so
# it stays PID 1 for clean container lifecycle management.
set -e

touch /var/log/opencanary/opencanary.log
python3 /opt/forward.py &

exec opencanaryd --start --uid=root --gid=root -f
