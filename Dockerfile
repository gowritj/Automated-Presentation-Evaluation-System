FROM python:3.11-slim

# System deps (OpenCV, ffmpeg, mediapipe)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Install Python deps — requirements.txt is UTF-16; convert first
RUN python -c "
import codecs, pathlib
src = pathlib.Path('requirements.txt').read_bytes()
try:
    txt = src.decode('utf-16')
except Exception:
    txt = src.decode('utf-8', errors='replace')
pathlib.Path('requirements_utf8.txt').write_text(txt)
"
RUN pip install --no-cache-dir -r requirements_utf8.txt
RUN pip install --no-cache-dir celery==5.4.0 redis==5.0.8
