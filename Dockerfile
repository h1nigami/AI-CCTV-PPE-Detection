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
    g++ \
    && rm -rf /var/lib/apt/lists/*

# ── Python зависимости ─────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 \
    opencv-python-headless \
    flask \
    waitress \
    pillow \
    ultralytics \
    numpy \
    insightface \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    2>&1 | tail -10

# ── Код приложения ─────────────────────────────────────────
COPY . .
RUN mkdir -p uploads models data

EXPOSE 8000
CMD ["python3", "-u", "app.py"]
