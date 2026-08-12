# Fake internal web portal: a believable-looking company intranet
# login/landing page. Purely cosmetic decoy -- no real auth, no real data.
FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir flask==3.0.3

COPY app.py /app/app.py

EXPOSE 80

CMD ["python", "app.py"]
