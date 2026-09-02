FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install FFmpeg + FFprobe required for audio playback
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r hexiron && useradd -r -g hexiron -d /app hexiron

# Create required directories
RUN mkdir -p /data/storage /data/temp /data/downloads /data/uploads /data/cache /data/logs \
    && chown -R hexiron:hexiron /data /app

COPY requirements.txt .

RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY . .

# Ensure the app owns its files
RUN chown -R hexiron:hexiron /app

USER hexiron

# Health check: verify the Python process is running
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD pgrep -f "python main.py" || exit 1

CMD ["python", "main.py"]
