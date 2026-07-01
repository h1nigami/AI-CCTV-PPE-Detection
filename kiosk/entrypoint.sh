#!/bin/sh
# Ждёт готовности бэкенда (/health) и запускает Chromium в режиме киоска.
# URL и профиль — через env (см. docker-compose.yml, сервисы kiosk-cpu/kiosk-gpu).
set -e

URL="${KIOSK_URL:-http://localhost:8000}"
HEALTH_URL="$(echo "$URL" | sed 's:/*$::')/health"
PROFILE_DIR="${KIOSK_PROFILE_DIR:-/data/chromium-profile}"

echo "Ожидание бэкенда: $HEALTH_URL"
until curl -fsS "$HEALTH_URL" >/dev/null 2>&1; do
    sleep 2
done
echo "Бэкенд готов. Запуск Chromium в режиме киоска: $URL"

mkdir -p "$PROFILE_DIR"

# --no-sandbox: chromium в контейнере без доп. capabilities не может поднять
# свой sandbox (нужны user namespaces/seccomp, обычно урезанные в Docker);
# это стандартный компромисс для контейнеризированного Chromium.
exec chromium \
    --kiosk "$URL" \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --noerrdialogs \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --disable-translate \
    --disable-features=TranslateUI \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    --no-sandbox \
    --window-position=0,0 \
    --start-fullscreen
