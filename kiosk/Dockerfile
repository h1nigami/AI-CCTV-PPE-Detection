# Контейнер с Chromium в режиме киоска. Рисует окно на дисплей-сервере ХОСТА
# (не headless) — на Windows это работает через WSLg (Docker Desktop, WSL2-движок,
# Windows 11), на Linux-хосте — через обычный X11 (см. docker-compose.yml).
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    ca-certificates \
    curl \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
