# 👷 AI CCTV PPE Detection System

**Система видеоаналитики реального времени** для контроля СИЗ на основе YOLOv8. Детектирует людей, каски, маски, жилеты, опасные зоны, распознаёт лица (Re-ID) и жесты. Включает адаптивный веб-интерфейс (десктоп/планшет/мобильный), ленту событий с видеоклипами, авторизацию и MinIO-хранилище.

---

## 🚀 Возможности

### Детекция & аналитика
- **Режимы детекции** — выбор «Люди / СИЗ / Лица» через UI; выключение всех режимов пропускает YOLO полностью
- **Живой стрим** — RTSP/IP камеры, JPEG load-driven поллинг (следующий кадр запрашивается после загрузки предыдущего — не забивает соединения)
- **СИЗ** — каски, маски, жилеты с цветовыми статусами рамок
- **Опасные зоны** — автоматическое построение по расположению конусов безопасности; на `/upload` (фото/видео) помечается, находится ли человек в зоне
- **Re-ID лиц** — InsightFace (buffalo_l), адаптивный порог (качество лица), auto-merge дубликатов, усиленная «липкость» личности к треку, до 30 ракурсов на человека («со всех сторон»), бессрочное хранение
- **ByteTrack** — стабильные track_id между кадрами, `track_buffer: 90`
- **Жест ОК** — распознавание жеста для пропуска в зону
- **Динамические face workers** — запуск/остановка потока распознавания лиц по чекбоксу
- **Motion detection (MOG2)** — опциональный гейт «Motion First»: на статичной сцене тяжёлая YOLO-детекция пропускается (экономия CPU). Включается `MOTION_DETECTION_ENABLED` (по умолчанию выкл.)

### Мониторинг & интеграции (Frigate-слой)
- **MQTT-шина событий** — публикация детекций/нарушений/heartbeat в брокер (eclipse-mosquitto): топики `frigate/<cam>/{motion,detection,violation,approved}` + `system/heartbeat`. Опционально, мягко деградирует без брокера/`paho-mqtt`. Включается `MQTT_ENABLED`
- **Home Assistant** — авто-обнаружение через MQTT discovery (сенсоры движения, людей, нарушений) при `MQTT_HA_DISCOVERY`
- **Метрики** — `GET /api/stats` (JSON), `GET /metrics` (Prometheus): FPS, латентность детекции, счётчики кадров/событий, CPU/RAM/диск
- **Healthcheck** — `GET /health` (используется в docker-compose healthcheck)

### Управление
- **CRUD камер** — добавление/удаление/переименование через веб-интерфейс
- **Группы камер** — объединение камер в группы для фильтрации
- **Управление галереей лиц** — переименование, удаление, просмотр через UI
- **Авторизация** — JWT (admin/operator/viewer/api роли), refresh-токены

### События & хранение
- **Лента событий** — отдельная страница с фильтрами (камера, тип), превью, плеером
- **Видеоклипы** — запись MP4 (H.264) при нарушениях с пост-кадрами
- **Снэпшоты** — кадр из середины клипа
- **MinIO** — S3-совместимое хранилище для клипов и снимков
- **Локальный fallback** — `violation_logs/` при недоступности MinIO
- **Логирование** — история событий с временными метками, категориями, именем человека
- **Экспорт CSV** — выгрузка логов
- **Уведомления** — всплывающие оповещения в браузере о пропусках и нарушениях

### Фронтенд
- **Адаптивный дизайн** — 3 брейкпоинта: мобильный (<768) / планшет (768–1199) / десктоп (≥1200)
- **Mobile drawer** — гамбургер-меню с навигацией, режимами детекции, старт/стоп
- **BottomSheets** — информация о камере на мобильных устройствах
- **FAB** — плавающие кнопки для быстрых действий на мобильных
- **Токены дизайна** — единая система цветов, отступов, радиусов, шрифтов

### Загрузка файлов
- **Изображения** — загрузка для детекции; результат скачивается через `<a download>`
- **Видео** — загрузка для детекции; результат скачивается как MP4

---

## 🛠️ Технологии

| Компонент | Технология |
|-----------|-----------|
| Backend | Python 3.11+, Flask, OpenCV, Ultralytics YOLOv8 |
| Frontend | Vite 6 + React 19 + TypeScript |
| Re-ID | InsightFace (buffalo_l) + ONNX Runtime (CPU / GPU) |
| Позы | YOLOv8n-pose (жесты) |
| Визуализация | PIL/Pillow (кириллица) |
| Трекинг | ByteTrack (ultralytics) |
| Хранилище | MinIO (S3) + local fallback |
| БД | SQLAlchemy + SQLite |
| Сервер | Waitress (production WSGI) |
| Контейнеры | Docker multi-stage (CPU / GPU / Jetson / nginx-фронт) + docker compose |
| Деплой | `deploy.sh` / `deploy.ps1` + git-хук pre-push (авто-деплой на серверы) |
| Тесты | pytest + pytest-cov (расширенное покрытие, CI на GitHub Actions) |

---

## 📦 Установка

### Требования
- Docker & Docker Compose (рекомендуется)
- Python 3.11+ (для локального запуска)

### 1. Клонировать
```bash
git clone https://github.com/your-username/AI-CCTV-PPE-Detection.git
cd AI-CCTV-PPE-Detection
```

### 2. Модели

YOLO-модели (`.pt`) встроены в репозиторий:

```
models/
├── best.pt              ← YOLOv8 PPE
├── yolov8n-pose.pt      ← жесты
├── yolov8n.pt           ← лица
└── buffalo_l/           ← InsightFace (скачать)
    ├── det_10g.onnx
    └── w600k_r50.onnx
```

InsightFace buffalo_l (~190 MB) — `models/buffalo_l/` в `.gitignore`, после клона докачивается:
```bash
python download_models.py            # идемпотентно: качает, только если модели нет
```
В Docker модель докачивается в рантайме (`entrypoint.sh`), т.к. `./models` монтируется volume'ом. Ручная альтернатива:
```bash
mkdir -p models/buffalo_l
wget -qO /tmp/buffalo_l.zip \
  "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
unzip -q -o /tmp/buffalo_l.zip -d models/buffalo_l/
rm /tmp/buffalo_l.zip
```

### 3. Запуск

```bash
# Быстрый старт (CPU)
docker compose --profile cpu up --build -d

# GPU (NVIDIA CUDA)
docker compose --profile gpu up --build -d
```

Открыть: `http://localhost:8000`  
Логин: `admin` / пароль: `admin123` (переопределяется через `ADMIN_PASSWORD`)

### Локальная разработка
```bash
pip install -r requirements.txt
python app.py
# Фронтенд: cd frontend && npm run dev
```

---

## ⚙️ Конфигурация

Основные настройки в `backend/config.py`:

```python
CAMERAS = {"cam1": "rtsp://admin:pass@192.168.1.100:554/stream1"}
CONF_THRESH = 0.75
REID_SIM_THRESHOLD = 0.55          # базовый порог (адаптивный 0.45–0.60)
REID_MAX_EMBEDDINGS = 30           # ракурсов на личность («со всех сторон»)
REID_MAX_AGE_DAYS = 0              # 0 = хранить бессрочно (авто-удаление выкл.)
REID_DIVERSITY_MAX_SIM = 0.92      # копим разные ракурсы, не дубли кадра
REID_STICKY_MARGIN = 0.25          # удержание личности за треком (анти-перезапись)
REID_STICKY_MIN = 0.28
EVENT_CLIP_FPS = 10                # FPS видео-клипов
EVENT_PRE_FRAMES = 30              # кадров до нарушения
EVENT_POST_FRAMES = 30             # кадров после разрешения
EVENT_MAX_FRAMES = 300             # макс. кадров клипа
MINIO_ENDPOINT = "minio:9000"
MINIO_BUCKET_EVENTS = "events"

# Frigate-слой (по умолчанию выключен, не меняет поведение)
MOTION_DETECTION_ENABLED = False   # MOG2-гейт перед YOLO (экономия CPU)
MOTION_MIN_AREA = 1500             # мин. площадь контура движения (px²)
MQTT_ENABLED = False               # публикация событий в MQTT-брокер
MQTT_HA_DISCOVERY = False          # Home Assistant MQTT discovery
```

Окружение (`.env`):
```ini
JWT_SECRET=your-random-secret
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-password
# Frigate-слой (опционально)
MOTION_DETECTION_ENABLED=true
MQTT_ENABLED=true
MQTT_HOST=mqtt
MQTT_PORT=1883
MQTT_TOPIC_PREFIX=frigate
MQTT_HA_DISCOVERY=true
```

---

## 🗂️ Структура проекта

```
backend/
├── app.py                 # Flask entrypoint
├── config.py              # Константы
├── main.py                # Оркестратор (start/stop, detection_loop, recording)
├── core/
│   ├── state.py           # DetectionState (треки, пропуска, логи, жесты)
│   ├── metrics.py         # MetricsRegistry (FPS, латентность, события)
│   └── models.py          # LogEntry
├── mqtt/
│   └── publisher.py       # MqttPublisher (события + HA discovery)
├── capture/
│   ├── buffer.py          # FrameBuffer
│   └── camera.py          # CameraCapture (RTSP/ffmpeg/local)
├── detection/
│   ├── engine.py          # run_detection, danger_zone
│   └── motion.py          # MotionDetector (MOG2 «Motion First»)
├── gestures/
│   └── detector.py        # detect_ok_gesture, detect_raised_hand
├── reid/
│   ├── gallery.py         # FaceGallery (адаптивный порог, merge)
│   ├── recognizer.py      # FaceRecognizer + FaceRecognitionWorker
│   └── worker.py          # FaceDetector (YOLO face)
├── visualization/
│   └── renderer.py        # put_text, draw_person, draw_legend
├── storage/
│   └── minio_client.py    # EventStorage (MinIO + local fallback)
├── db/
│   ├── engine.py          # SQLAlchemy engine
│   └── models.py          # Event, User, Camera, ApiKey
├── auth/
│   ├── routes.py          # login/refresh/me
│   └── service.py         # JWT, init_admin
└── api/
    ├── detection.py       # /start, /stop, /video_feed, /detect-modes, /upload
    ├── cameras.py         # CRUD камер + группы
    ├── reid.py            # Управление галереей лиц
    ├── events.py          # События: GET, clip, snapshot
    └── monitoring.py      # /health, /metrics, /api/stats

frontend/
├── src/
│   ├── App.tsx            # Роутинг (Dashboard, Events, Settings, Login)
│   ├── components/
│   │   ├── Header.tsx     # Навигация, режимы детекции, mobile drawer
│   │   ├── CameraCard.tsx # Карточка камеры (JPEG load-driven поллинг)
│   │   ├── CameraGrid.tsx # Адаптивная сетка камер
│   │   ├── Dashboard.tsx  # Главная: 3 breakpoint layout
│   │   ├── LeftPanel.tsx  # Информационная панель
│   │   ├── DispatcherPanel.tsx
│   │   └── ui/            # Box, Flex, Grid, Responsive, BottomSheet
│   ├── pages/
│   │   ├── EventsPage.tsx # Лента событий с фильтрами и плеером
│   │   └── SettingsPage.tsx
│   ├── contexts/
│   │   ├── CameraContext.tsx
│   │   └── AuthContext.tsx
│   ├── hooks/
│   │   ├── useBreakpoint.ts
│   │   ├── useOrientation.ts
│   │   └── useClock.ts
│   └── api/
│       └── client.ts      # HTTP-клиент с JWT refresh
```

---

## 🔧 Производительность

- **Параллельная детекция** — поток детекции на каждую камеру (свой экземпляр YOLO), камеры обрабатываются одновременно; нативные либы (YOLO/InsightFace/OpenCV) отпускают GIL → реальный параллелизм на CPU-ядрах (на одном GPU агрегатный FPS ограничен GPU)
- **JPEG load-driven поллинг** — `/video_frame/<cam_id>`: следующий кадр запрашивается из `onload` предыдущего (без `setInterval`, не забивает пулы соединений/Waitress)
- **Re-ID** — распознавание каждый `REID_FRAME_SKIP` (3) кадр; порог матчинга адаптивный 0.45–0.60
- **ByteTrack** — `persist=True` + `track_buffer: 90` для стабильных ID
- **FFmpeg subprocess** — чтение RTSP через ffmpeg, корректный PID cleanup
- **GPU (CUDA)** — Jetson через `--runtime nvidia`; CPU ~1-2 FPS без GPU

## 🎯 Статусы людей

| Цвет рамки | Статус |
|-----------|--------|
| 🟢 Зелёный | Все СИЗ, вне зоны |
| 🟠 Оранжевый | В зоне, СИЗ есть |
| 🔴 Красный | В зоне, нарушение СИЗ |
| 🟡 Жёлтый | Вне зоны, нет СИЗ |
| 🟤 Золотой | Пропуск выдан |

---

## 📋 API

### Детекция
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `POST` | `/start` | Запуск детекции |
| `POST` | `/stop` | Остановка детекции |
| `GET` | `/api/status` | Статус (running: bool) |
| `GET` | `/api/detect-modes` | Получить режимы |
| `PUT` | `/api/detect-modes` | Установить режимы |

### События
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/events` | Список событий (camera, label, limit, offset) |
| `GET` | `/api/events/<id>` | Детали события |
| `GET` | `/api/events/<id>/clip` | Видеоклип (MP4) |
| `GET` | `/api/events/<id>/snapshot` | Снимок (JPEG) |

### Re-ID
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/reid/persons` | Список личностей |
| `POST` | `/api/reid/persons/<id>/rename` | Переименовать |
| `DELETE` | `/api/reid/persons/<id>` | Удалить |
| `GET` | `/api/reid/stats` | Статистика |

### Камеры
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/cameras` | Список камер |
| `POST` | `/api/cameras` | Добавить камеру |
| `PUT` | `/api/cameras/<id>` | Обновить камеру |
| `DELETE` | `/api/cameras/<id>` | Удалить камеру |

### Авторизация
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `POST` | `/auth/login` | Вход |
| `POST` | `/auth/refresh` | Refresh токена |
| `GET` | `/auth/me` | Текущий пользователь |

### Мониторинг
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/health` | Healthcheck (status, uptime) |
| `GET` | `/metrics` | Метрики в формате Prometheus |
| `GET` | `/api/stats` | Метрики в JSON (FPS, латентность, события, система) |

---

## 🔁 Docker Compose

```bash
# CPU profile (по умолчанию)
docker compose --profile cpu up --build -d

# GPU profile
docker compose --profile gpu up --build -d

# Остановка
docker compose --profile cpu down

# Dev (hot-reload кода)
docker compose --profile cpu up -d
# Python-изменения → restart
docker compose --profile cpu restart app-cpu
# React-изменения → cd frontend && npm run build → restart
```

Сервисы:
- `app-cpu` / `app-gpu` — основное приложение
- `minio` — S3-хранилище клипов (порт 9000 API, 9002 console)
- `createbuckets` — инициализация bucket'ов при старте
- `mqtt` — Mosquitto брокер для шины событий (включается `MQTT_ENABLED`, см. Frigate-слой)

Все сервисы имеют healthcheck (`app-cpu`/`app-gpu` — через `GET /health`).

---

## 🚢 Деплой на серверы

Бэкенд и фронтенд можно разнести на разные машины: бэк (GPU, Docker) на одном сервере, фронт (nginx reverse-proxy, раздаёт собранный React и проксирует API) — на другом. Браузер общается только с фронт-сервером (один origin → без CORS).

```bash
./deploy.sh backend            # код бэка → бэк-сервер + restart
./deploy.sh backend --build    # + пересборка образа (после правок зависимостей/Dockerfile)
./deploy.sh frontend           # фронт → фронт-сервер + пересборка nginx
./deploy.sh all                # оба
.\deploy.ps1 all               # из Windows PowerShell (обёртка ищет Git Bash)
```

- **Все адреса серверов — в `deploy.env`** (`BACKEND_HOST`, `FRONTEND_HOST`, каталоги, `BACKEND_URL`). При смене серверов правится **только этот файл**.
- `deploy.sh` переносит код по ssh (tar-туннель), не зависит от git на серверах. Модели/`data` не переносит — на новый бэк доставить вручную (`python download_models.py` + `data/`).
- **Авто-деплой при `git push` в `main`** через git-хук. Подключить один раз:
  ```bash
  git config core.hooksPath scripts/git-hooks
  ```
  Пропустить разово: `SKIP_DEPLOY=1 git push`.
- Фронт-сервер: `Dockerfile.frontend` + `docker-compose.frontend.yml` (nginx, `BACKEND_URL` из `deploy.env`). Подробности — `DEPLOY_FRONTEND_CHECKLIST.md`.

---

## 🧪 Тестирование

```bash
# В контейнере (автоматически перед стартом)
python3 -m pytest tests/ -v --tb=short

# Локально
pip install -r requirements.txt
python3 -m pytest tests/ -v --cov=backend
```

Расширенный набор тестов: галерея, состояние, движок, конфиг, API (камеры/Re-ID), auth, БД, хранилище, буфер, жесты, распознавание. CI прогоняет их на GitHub Actions; в dev-контейнере pytest идёт перед стартом приложения.

---

## 📄 Лицензия

MIT © 2026
