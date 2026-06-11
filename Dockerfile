# ============================================================
# Dockerfile (x86_64 + ARM64)
# Для RTSP камер используется GStreamer или ffmpeg
# ============================================================
# Сборка: docker build -t ppe-detection .
# Для ARM64 с GPU (Jetson) используйте Dockerfile.jetson
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# ── Системные зависимости ──────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
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

# PyTorch с автовыбором под архитектуру:
#   x86_64 → CPU-only wheels (меньше размер)
#   ARM64  → PyPI (есть aarch64 wheels)
RUN if [ "$(uname -m)" = "aarch64" ]; then \
        pip install --no-cache-dir --timeout=300 \
            torch==2.12.0 \
            torchvision==0.27.0; \
    else \
        pip install --no-cache-dir --timeout=300 \
            torch==2.12.0+cpu \
            torchvision==0.27.0+cpu \
            --extra-index-url https://download.pytorch.org/whl/cpu; \
    fi

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
CMD ["python3", "-u", "app.py"]
