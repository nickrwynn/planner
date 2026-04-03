FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for OCR (optional, used when available)
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*

# Reuse API requirements so worker can import `app.*` indexing/parsing code.
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/worker /app
COPY apps/api/app /app/app

# In docker-compose, ./apps/worker is mounted on /app; keep ./apps/api/app mounted at /app/app so imports match this layout.
CMD ["python", "-m", "worker.main"]

