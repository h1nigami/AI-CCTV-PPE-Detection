#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Деплой на серверы одной командой. Источник истины — ТЕКУЩИЙ рабочий каталог
# (то, что вы закоммитили). Код переносится по ssh (tar-туннель) и сервис
# перезапускается/пересобирается. НЕ зависит от git-состояния серверов и не
# трогает модели/data/галерею на них.
#
# Использование:
#   ./deploy.sh backend          код бэка → tesla, restart (быстро, bind-mount)
#   ./deploy.sh backend --build  то же + пересборка образа (после правок зависимостей/Dockerfile)
#   ./deploy.sh frontend         фронт → jetson, пересборка nginx-образа
#   ./deploy.sh all              и бэк, и фронт
#
# Адреса серверов — в deploy.env (правится в ОДНОМ месте при смене серверов).
# Требует: ssh-ключ на обоих серверах (уже настроен), bash+tar (Git Bash на Windows).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Конфигурация серверов ────────────────────────────────────────────────────
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# Единый источник адресов — deploy.env (правится при смене серверов).
if [ -f "$REPO_DIR/deploy.env" ]; then
  set -a; . "$REPO_DIR/deploy.env"; set +a
fi
# Фоллбэк-дефолты, если deploy.env отсутствует.
BACKEND_HOST="${BACKEND_HOST:-best@192.168.0.97}"
BACKEND_DIR="${BACKEND_DIR:-AI-CCTV-PPE-Detection}"          # относительно $HOME на сервере
FRONTEND_HOST="${FRONTEND_HOST:-nvidia@192.168.0.85}"
FRONTEND_DIR="${FRONTEND_DIR:-kontroller-frontend}"

SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
err() { printf '\033[1;31m!! %s\033[0m\n' "$*" >&2; }

# Файлы бэка, которые реально нужны на сервере (совпадают с bind-mount'ами
# docker-compose.override.yml + то, что требуется для пересборки образа).
# НЕ переносим: models/, data/, .venv, .git, uploads/, violation_logs/, node_modules.
BACKEND_PATHS=(
  backend app.py config.py main.py state.py camera.py detection.py
  gestures.py visualization.py reid.py migrations tests
  requirements.txt Dockerfile Dockerfile.gpu docker-compose.yml
  docker-compose.override.yml entrypoint.sh export_models.py download_models.py
)

deploy_backend() {
  local build="$1"
  log "Бэкенд → $BACKEND_HOST:~/$BACKEND_DIR"
  ssh $SSH_OPTS "$BACKEND_HOST" "mkdir -p ~/$BACKEND_DIR"
  tar --exclude='__pycache__' --exclude='*.pyc' -cf - "${BACKEND_PATHS[@]}" \
    | ssh $SSH_OPTS "$BACKEND_HOST" "tar -xf - -C ~/$BACKEND_DIR"
  log "Код перенесён. Перезапуск сервиса…"
  if [ "$build" = "build" ]; then
    ssh $SSH_OPTS "$BACKEND_HOST" "cd ~/$BACKEND_DIR && docker compose --profile gpu up -d --build app-gpu"
  else
    # bind-mount уже подтянул код — достаточно restart (pytest-гейт прогонится)
    ssh $SSH_OPTS "$BACKEND_HOST" "cd ~/$BACKEND_DIR && docker compose --profile gpu restart app-gpu"
  fi
  log "Проверка /api/status…"
  ssh $SSH_OPTS "$BACKEND_HOST" \
    'for i in $(seq 1 40); do curl -sf -m3 http://127.0.0.1:8000/api/status && break; sleep 2; done'
  echo
}

deploy_frontend() {
  log "Фронтенд → $FRONTEND_HOST:~/$FRONTEND_DIR"
  ssh $SSH_OPTS "$FRONTEND_HOST" "mkdir -p ~/$FRONTEND_DIR"
  # deploy.env нужен на сервере: docker-compose.frontend.yml читает его как env_file
  tar --exclude='node_modules' --exclude='dist' -cf - \
    frontend Dockerfile.frontend docker-compose.frontend.yml deploy.env \
    | ssh $SSH_OPTS "$FRONTEND_HOST" "tar -xf - -C ~/$FRONTEND_DIR"
  log "Код перенесён. Пересборка nginx-образа…"
  # docker compose v2 (поддерживает profiles в compose-файле); поднимаем только
  # сервис frontend-web (mediamtx — опциональный профиль webcam, не трогаем).
  ssh $SSH_OPTS "$FRONTEND_HOST" \
    "cd ~/$FRONTEND_DIR && docker compose -f docker-compose.frontend.yml up -d --build frontend-web"
  log "Проверка фронта (http://<jetson>/api/status через nginx)…"
  ssh $SSH_OPTS "$FRONTEND_HOST" \
    'for i in $(seq 1 15); do curl -sf -m3 http://127.0.0.1/api/status && break; sleep 2; done'
  echo
}

TARGET="${1:-}"
BUILD_FLAG="restart"
[ "${2:-}" = "--build" ] && BUILD_FLAG="build"

case "$TARGET" in
  backend)  deploy_backend "$BUILD_FLAG" ;;
  frontend) deploy_frontend ;;
  all)      deploy_backend "$BUILD_FLAG"; deploy_frontend ;;
  *)
    err "Укажите цель: backend | frontend | all   (опц. backend --build)"
    exit 1
    ;;
esac

log "Деплой завершён."
