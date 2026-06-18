# Чек-лист: деплой фронта на отдельный сервер (nginx reverse-proxy → бэк)

> Рабочий трекер. Статусы: `[x]` сделано · `[~]` в процессе · `[ ]` не начато · `[blocked]` ждёт внешнего.
> Обновляется по ходу выполнения.

## Контекст
Бэкенд работает в Docker на GPU-сервере `192.168.0.97:8000` (Tesla P4, RTSP-камера, MinIO/MQTT).
Фронт выносим на **отдельный сервер**: nginx раздаёт собранный React и проксирует все API/медиа-пути
на бэк. Браузер видит один origin → без CORS/mixed-content/проблем MJPEG, код фронта не меняется
(`client.ts` `BASE=""`). Без HTTPS (http по IP). Бэк :8000 остаётся открытым.

## Архитектура
```
Браузер ─http─> [ФРОНТ-СЕРВЕР nginx :80]
                   ├─ /        → статика dist (React SPA)
                   └─ /api,/video_*,/start,/stop,/cameras,/detection_log,/export_logs,/upload
                        ──proxy_pass──> http://192.168.0.97:8000  [БЭК Docker]
```

---

## Подготовка (без фронт-сервера) ✅ ГОТОВО
- [x] `Dockerfile.frontend` — multi-stage node→nginx
- [x] `frontend/nginx.conf.template` — SPA-фоллбэк + reverse-proxy на `${BACKEND_URL}`, `proxy_buffering off` для MJPEG
- [x] `docker-compose.frontend.yml` — сервис `frontend-web`, `80:80`, `BACKEND_URL`, `restart: unless-stopped`
- [x] Локальная проверка сборки фронта (`npm run build` → dist без ошибок) — built in 666 ms, 0 ошибок TS

## Фаза 0 — подключение/диагностика (нужен фронт-сервер)
- [blocked] Получить IP/доступ к фронт-серверу, установить SSH-ключ
- [ ] Зафиксировать ОС, наличие Docker/compose
- [ ] Связность с бэком: с фронт-сервера `curl http://192.168.0.97:8000/api/status` → 200

## Фаза 1 — ПО на фронт-сервере
- [ ] Если нет Docker: `docker.io` + `docker-compose-v2`, юзер в группу docker

## Фаза 2 — доставка и запуск
- [ ] Скопировать `frontend/` (без node_modules/dist) + `Dockerfile.frontend`, `frontend/nginx.conf.template`, `docker-compose.frontend.yml`
- [ ] `docker compose -f docker-compose.frontend.yml up -d --build` → nginx на `:80`

## Фаза 3 — верификация e2e
- [ ] С фронт-сервера `curl http://192.168.0.97:8000/api/status` → 200
- [ ] `curl http://<FRONT_SERVER>/api/status` (через nginx) → 200
- [ ] Браузер `http://<FRONT_SERVER>/` → UI, вход `admin/admin123`, видны камеры
- [ ] `/video_frame` отдаёт кадры; `/video_feed/<cam>` стримит (MJPEG)
- [ ] Вкладка событий открывает клипы; логи nginx без ошибок проксирования

---

## Критичные файлы
- Новые: `Dockerfile.frontend`, `frontend/nginx.conf.template`, `docker-compose.frontend.yml`
- Не меняются: `frontend/src/api/client.ts` (`BASE=""`), бэк целиком
- `frontend/vite.config.ts` — на прод-фронт не влияет (только локальный dev)

## Риски
- MJPEG зависает → `proxy_buffering off` + `proxy_read_timeout`
- SPA-роуты 404 → `try_files $uri /index.html`
- Фронт-сервер не видит бэк → проверка на Фазе 0
- Смена IP бэка → поменять `BACKEND_URL` в compose и пересоздать контейнер (код не пересобирать)
