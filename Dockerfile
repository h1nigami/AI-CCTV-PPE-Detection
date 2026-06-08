FROM dustynv/pytorch:2.1-r36.2.0

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu-core \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY wheels/ /wheels/
RUN pip install --no-index --find-links=/wheels \
    ultralytics==8.4.60 \
    opencv-python-headless \
    flask \
    waitress \
    pillow \
    "numpy<2.0"

COPY . .
RUN mkdir -p uploads

EXPOSE 8000
CMD ["python", "app.py"]