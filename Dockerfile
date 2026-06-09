FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu-core \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --timeout=300 \
    torch \
    torchvision \
    ultralytics==8.4.60 \
    opencv-python-headless \
    flask==2.3.3 \
    waitress==2.1.2 \
    pillow \
    "numpy<2.0"

COPY . .
RUN mkdir -p uploads

EXPOSE 8000
CMD ["python", "app.py"]