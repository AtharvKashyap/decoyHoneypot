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
ENTRYPOINT ["/usr/bin/samba.sh"]
CMD ["-p", "-w", "MERIDIAN", \
     "-s", "company;/share;yes;no;yes;everyone;none;none;Meridian Logistics file share", \
     "-n"]
