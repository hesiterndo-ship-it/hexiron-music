FROM python:3.11-slim

WORKDIR /app

# FFmpeg + FFprobe
COPY --from=mwader/static-ffmpeg:9.0.1 /ffmpeg /usr/local/bin/ffmpeg
COPY --from=mwader/static-ffmpeg:9.0.1 /ffprobe /usr/local/bin/ffprobe

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
