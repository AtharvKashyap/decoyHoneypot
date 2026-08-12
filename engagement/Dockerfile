# Build from the REPO ROOT context (the tarpit imports the shared core/ and
# config/ packages):
#   docker build -f engagement/Dockerfile .
FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" PyYAML anthropic

COPY core/ core/
COPY config/ config/
COPY engagement/ engagement/

ENV EVENTS_DB=/data/events.db PYTHONUNBUFFERED=1 TARPIT_DELAY_MS=0
EXPOSE 8080
CMD ["uvicorn", "engagement.app:app", "--host", "0.0.0.0", "--port", "8080"]
