# Build from the REPO ROOT context (the hub imports the shared core/ package):
#   docker build -f hub/Dockerfile .
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" jinja2 PyYAML

COPY core/ core/
COPY config/ config/
COPY hub/ hub/

ENV EVENTS_DB=/data/events.db PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "hub.app:app", "--host", "0.0.0.0", "--port", "8000"]
