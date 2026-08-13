#!/bin/sh
# Start rsyslog (captures Samba's full_audit messages to the shared log file),
# then run smbd in the foreground as PID 1.
set -e

mkdir -p /var/log/samba/audit /run/samba /var/lib/samba/private
touch /var/log/samba/audit/audit.log

# Create the shared "employee" Samba account personas authenticate with, so
# their reads are attributed to a known user in the audit log (the attacker,
# by contrast, connects anonymously and is mapped to guest/nobody).
EMP_USER="${SMB_EMPLOYEE_USER:-employee}"
EMP_PASS="${SMB_EMPLOYEE_PASS:-labpass}"
useradd -M -s /usr/sbin/nologin "$EMP_USER" 2>/dev/null || true
printf '%s\n%s\n' "$EMP_PASS" "$EMP_PASS" | smbpasswd -a -s "$EMP_USER"

# rsyslogd reads /dev/log (imuxsock) and writes local7.* to the audit file.
rsyslogd

exec smbd --foreground --no-process-group
