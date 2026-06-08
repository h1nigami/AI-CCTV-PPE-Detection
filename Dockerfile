# Базовый образ NVIDIA для Jetson с уже установленным PyTorch
FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu-core \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# PyTorch уже есть в образе, ставим только остальное
COPY requirements.txt .
RUN pip install --no-cache-dir \
    ultralytics \
    opencv-python-headless \
    flask \
    waitress \
    pillow \
    numpy

COPY . .
RUN mkdir -p uploads

EXPOSE 8000
CMD ["python", "app.py"]