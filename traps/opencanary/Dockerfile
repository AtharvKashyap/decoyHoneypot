# OpenCanary multi-service tripwire: any connection/probe to ftp/http/mysql/
# smb here is inherently attacker activity (personas never touch this host).
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libssl-dev libffi-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir opencanary

RUN mkdir -p /etc/opencanaryd /var/log/opencanary
COPY opencanary.conf /etc/opencanaryd/opencanary.conf

# NOTE on forwarder.py: docker-compose.yml builds this image with context
# `./traps/opencanary` (scoped per service, not editable here), so this
# directory carries a same-content copy of the shared `traps/forwarder.py`
# helper -- see traps/README.md.
COPY forwarder.py /opt/forwarder.py
COPY forward.py /opt/forward.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh /opt/forward.py

ENV HUB_URL=http://hub:8000
ENV OPENCANARY_LOG=/var/log/opencanary/opencanary.log

EXPOSE 21 80 3306 445

ENTRYPOINT ["/opt/entrypoint.sh"]
