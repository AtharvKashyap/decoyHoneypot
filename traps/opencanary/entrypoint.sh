#!/bin/sh
# Start the log forwarder sidecar, then run opencanaryd in the foreground so
# it stays PID 1 for clean container lifecycle management.
set -e

touch /var/log/opencanary/opencanary.log
python3 /opt/forward.py &

# --dev runs opencanaryd in the FOREGROUND (twistd nodaemon), so it stays PID 1
# and the container doesn't exit. --start would daemonize and drop the process.
exec opencanaryd --dev
