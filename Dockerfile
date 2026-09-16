FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# CA certificates are required for HTTPS downloads
# FFmpeg is installed at runtime by utils/ffmpeg_setup.py
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create runtime directories
RUN mkdir -p \
        /data/storage \
        /data/temp \
        /data/downloads \
        /data/uploads \
        /data/cache \
        /data/logs \
        /data/bin

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy application
COPY . .

CMD ["python", "main.py"]