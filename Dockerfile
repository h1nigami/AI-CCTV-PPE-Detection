# ─────────────────────────────────────────────────────────
#  Stage 1: Сборка React frontend
# ─────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ─────────────────────────────────────────────────────────
#  Stage 2: Python runtime
# ─────────────────────────────────────────────────────────
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

# ── Собранный frontend из Stage 1 ──────────────────────────
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

EXPOSE 8000
CMD ["python3", "-u", "app.py"]
