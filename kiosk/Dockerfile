# Контейнер с Chromium в режиме киоска. Рисует окно на X11-дисплее ХОСТА
# (не headless) — см. docker-compose.yml (сервисы kiosk-cpu/kiosk-gpu) и
# docs/kiosk-mode.md про подготовку Linux-хоста (Xauthority/DISPLAY).
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    ca-certificates \
    curl \
    fonts-liberation \
    dbus \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
# sed -i убирает \r — если репозиторий выкачан на Windows с core.autocrlf=true,
# git конвертирует .sh в CRLF, и шебанг "#!/bin/sh\r" ломает exec с
# малопонятной ошибкой "no such file or directory". Не полагаемся на
# git-настройки хоста, чиним прямо при сборке образа.
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
