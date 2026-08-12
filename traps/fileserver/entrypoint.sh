#!/bin/sh
# Start rsyslog (captures Samba's full_audit messages to the shared log file),
# then run smbd in the foreground as PID 1.
set -e

mkdir -p /var/log/samba/audit /run/samba /var/lib/samba/private
touch /var/log/samba/audit/audit.log

# rsyslogd reads /dev/log (imuxsock) and writes local7.* to the audit file.
rsyslogd

exec smbd --foreground --no-process-group
