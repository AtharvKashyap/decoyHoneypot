# Build from the REPO ROOT context (the engine imports the shared core/ package):
#   docker build -f personas/Dockerfile .
FROM python:3.12-slim
WORKDIR /app

# smbclient lets personas perform real (best-effort) SMB activity in live mode.
RUN apt-get update && apt-get install -y --no-install-recommends smbclient \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir APScheduler requests paramiko PyYAML

COPY core/ core/
COPY config/ config/
COPY personas/ personas/

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "personas.run"]
