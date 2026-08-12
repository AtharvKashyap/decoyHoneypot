#!/usr/bin/with-contenv bash
# Create low-value local accounts matching the persona usernames from
# config/company.example.yaml, so persona SSH activity (jchen/rpatel/slee)
# has real accounts to authenticate against in the lab. Passwords are
# intentionally simple/synthetic -- this is an isolated, internet-cut-off
# decoy network with no real credentials or data.
set -e

declare -A USERS=(
  [jchen]="finance-2026"
  [rpatel]="devops-2026"
  [slee]="hrpeople-2026"
)

for username in "${!USERS[@]}"; do
  if ! id "$username" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$username"
  fi
  echo "${username}:${USERS[$username]}" | chpasswd
done
