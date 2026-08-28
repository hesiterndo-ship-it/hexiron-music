FROM python:3.11-slim

WORKDIR /app

# Static FFmpeg + FFprobe
COPY --from=mwader/static-ffmpeg:9.0.1 /ffmpeg /usr/local/bin/ffmpeg
COPY --from=mwader/static-ffmpeg:9.0.1 /ffprobe /usr/local/bin/ffprobe

# Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Application
COPY . .

CMD ["python", "main.py"]
