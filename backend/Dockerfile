FROM python:3.12-slim as builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

# Non-root user for security compliance
RUN useradd -m -u 1001 attendai

COPY --from=builder /root/.local /home/attendai/.local
COPY . /app

# Ensure correct permissions for non-root user across app and home
RUN mkdir -p /app/uploads && chown -R attendai:attendai /home/attendai /app && chmod -R 755 /home/attendai /app

ENV PATH=/home/attendai/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV UPLOAD_DIR=/app/uploads

USER attendai

EXPOSE 8000 10000

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
