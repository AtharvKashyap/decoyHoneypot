# Samba fileserver: the real, usable decoy share. Personas legitimately read
# and edit files here; attackers who pivot into the deception network can
# discover and pull the same (AI-generated, canaried) documents.
#
# docker-compose.yml mounts the `seed` volume (populated by the Decoy
# Generator) at /share, so the exact same directory tree personas use is what
# an attacker sees over SMB.
FROM dperson/samba:latest

# Anonymous/guest read access to a single "company" share rooted at /share.
# -p disables the container's default password prompt banner; -w sets a
# believable workgroup name for the fake org.
# Share fields are name;path;browsable;readonly;guest — leaving the `users`
# field empty keeps it public (a non-empty `users` becomes samba `valid users`
# and would DENY guests). Read-only matches the read-only seed mount.
ENTRYPOINT ["/usr/bin/samba.sh"]
CMD ["-p", "-w", "MERIDIAN", \
     "-g", "map to guest = Bad User", \
     "-g", "server min protocol = NT1", \
     "-s", "company;/share;yes;yes;yes;;;;Meridian Logistics file share", \
     "-n"]
