# Plain SSH host personas legitimately log into (not a trap -- a real,
# usable jump box). Low-value local accounts mirror the persona usernames
# from config/company.example.yaml so the persona engine's simulated SSH
# activity has something real to connect to in the lab.
FROM linuxserver/openssh-server:latest

# linuxserver/openssh-server takes account config via env vars, but we also
# create the persona accounts directly for a config-free, deterministic
# build (matches config/company.example.yaml usernames).
COPY create_users.sh /etc/cont-init.d/50-create-users
RUN chmod +x /etc/cont-init.d/50-create-users

ENV PUID=1000
ENV PGID=1000
ENV TZ=Etc/UTC
ENV PASSWORD_ACCESS=true
ENV SUDO_ACCESS=false

EXPOSE 2222
