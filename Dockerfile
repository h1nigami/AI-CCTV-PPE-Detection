# ============================================================
# Мульти-архитектурный Dockerfile (x86_64 + ARM64)
# Для RTSP камер используется GStreamer (ARM64/Jetson) или ffmpeg
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# ── Системные зависимости ──────────────────────────────────
# GStreamer для RTSP на ARM64/Jetson, ffmpeg как fallback
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    # FFmpeg (fallback для RTSP)
    ffmpeg \
    # GStreamer (основной для RTSP на ARM64)
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Python зависимости ─────────────────────────────────────
COPY requirements.txt .

# PyTorch (тяжёлый — кешируем отдельно)
# На ARM64 (Jetson) используйте nvidia/l4t-pytorch базовый образ
# и закомментируйте эту строку
RUN pip install --no-cache-dir --timeout=300 \
    torch==2.12.0+cpu \
    torchvision==0.27.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Остальные зависимости
RUN pip install --no-cache-dir --timeout=300 \
    ultralytics==8.4.60 \
    opencv-python-headless==4.11.0.86 \
    flask==2.3.3 \
    waitress==2.1.2 \
    pillow \
    "numpy<2.0"

# ── Код приложения ─────────────────────────────────────────
COPY . .
RUN mkdir -p uploads models

EXPOSE 8000
CMD ["python", "-u", "app.py"]
