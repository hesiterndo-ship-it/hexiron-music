FROM python:3.11-bookworm-slim

WORKDIR /app

# FFmpeg + FFprobe
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Application
COPY . .

CMD ["python", "main.py"]
