FROM dustynv/pytorch:2.0-r35.3.1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu-core \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir \
    ultralytics==8.4.60 \
    opencv-python-headless \
    "flask~=3.1.3" \
    "waitress~=3.0.2" \
    pillow \
    "numpy<2.0"

COPY . .
RUN mkdir -p uploadss

EXPOSE 8000
CMD ["python","app.py"]
