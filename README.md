# 👷 AI CCTV PPE Detection System

**Система видеоаналитики реального времени** для контроля СИЗ на основе YOLOv8. Детектирует людей, каски, маски, жилеты, опасные зоны, распознаёт лица (Re-ID) и жесты. Включает адаптивный веб-интерфейс (десктоп/планшет/мобильный), ленту событий с видеоклипами, авторизацию и MinIO-хранилище.

---

## 🚀 Возможности

### Детекция & аналитика
- **Режимы детекции** — выбор «Люди / СИЗ / Лица» через UI; при выключении всех режимов YOLO пропускается, но **живой стрим продолжается** (отдаётся сырой кадр, останавливается только детекция). Режим «только люди» выделяет людей нейтральной рамкой без статусов СИЗ/пропуска
- **Живой стрим** — RTSP/IP камеры, JPEG load-driven поллинг (следующий кадр запрашивается после загрузки предыдущего — не забивает соединения). При потере камеры показывается **«NO SIGNAL»** вместо замороженного кадра — и в поллинге `/video_frame` (204), и в MJPEG `/video_feed` (синтетический кадр)
- **СИЗ** — каски, маски, жилеты с цветовыми статусами рамок
- **Настройка обязательных СИЗ** — чекбоксы в «Настройки» (каска/маска/жилет): какой комплект нужен для выдачи пропуска по жесту «ОК». Сохраняется на бэке (`data/ppe_required.json`), панель «Статус проверки СИЗ» показывает только выбранные средства
- **Настройка детекции из UI** — вкладка «Настройки → Детекция и логика»: слайдерами/полями настраиваются пороги уверенности (человек/конус и СИЗ), параметры опасных зон по конусам (минимум конусов, расширение), зона засчёта СИЗ по высоте, время пропуска, кулдауны жеста и голоса. Применяется **на лету** без перезапуска, сохраняется на бэке (`data/detection_settings.json`); каждый параметр с описанием, диапазоном и сбросом к умолчанию. Панель рендерится по спеке с бэка (`/api/detection-settings`) — добавление нового параметра не требует правок фронта
- **Опасные зоны** — автоматическое построение по расположению конусов безопасности; на `/upload` (фото/видео) помечается, находится ли человек в зоне
- **Редактор зон** — рисование полигональных зон мышью поверх кадра (страница «Зоны»): опасные/ограниченные зоны и маски (исключение области из детекции); координаты нормализованные, hot-reload
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
- **CRUD камер** — добавление/удаление/переименование через веб-интерфейс (синхронизируется в БД)
- **Автообнаружение камер** — кнопка «Найти камеры»: поиск RTSP-камер в локальной сети (ONVIF WS-Discovery + скан подсети). Находит **и открытые** (поток без логина — добавляются одной кнопкой), **и запароленные** камеры (порт 554 открыт / ответил ONVIF, но без логина не открываются) — для них UI предлагает **ввести логин и пароль**, бэкенд подбирает рабочий RTSP-путь и добавляет камеру. **Работает без интернета** — сканируются подсети всех локальных интерфейсов (определяются через интерфейсы хоста, не зависят от маршрута в WAN). Опц. авто-добавление открытых при старте (`CAMERA_AUTODISCOVER`)
- **Группы камер** — объединение камер в группы для фильтрации
- **Управление галереей лиц** — переименование, удаление, просмотр через UI
- **Авторизация** — JWT (admin/operator/viewer/api роли), refresh-токены

### События & хранение
- **Лента событий** — отдельная страница с фильтрами (камера, тип), превью, плеером
- **Архив (NVR)** — страница «Архив»: выбор камеры/даты, 24-часовой таймлайн сегментов записи (пометка движения) с метками событий; клик по событию → переход к моменту в записи; плеер с перемоткой и непрерывным воспроизведением (авто-переход к следующему сегменту)
- **Видеоклипы** — запись MP4 (H.264) при нарушениях с пост-кадрами
- **Снэпшоты** — кадр из середины клипа
- **NVR (непрерывная запись)** — круглосуточный архив: ffmpeg режет RTSP на сегменты (`-c copy`, ~0% CPU), индекс в БД, retention по сроку/движению/диску. Режим `motion` экономит 80-90% диска. Опционально (`RECORD_ENABLED`)
- **MinIO** — S3-совместимое хранилище для клипов и снимков
- **Локальный fallback** — `violation_logs/` при недоступности MinIO
- **Логирование** — история событий с временными метками, категориями, именем человека
- **Экспорт CSV** — выгрузка логов
- **Уведомления** — всплывающие оповещения в браузере о пропусках и нарушениях
- **Голосовые предупреждения** — озвучивание входа без СИЗ в опасную зону. Основной путь — **синтез на бэкенде (Piper TTS, русский голос)**: фронт получает готовый WAV, качество не зависит от ОС оператора. Фоллбэк — Web Speech API браузера, если бэкенд-TTS недоступен (нужен русский голос в ОС, см. ниже). Доставка **курсорная** — несколько вкладок и несколько камер получают алерты независимо, без «съедания» одним клиентом и без сериализации по одному на опрос

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
| Синтез речи | Piper TTS (бэкенд) + Web Speech API (фоллбэк) |
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
CONF_THRESH = 0.75                 # порог уверенности для людей/конусов
PPE_CONF_THRESH = 0.5              # отдельный (мягче) порог для СИЗ: каска/маска/жилет (env)
PPE_REQUIRED_DEFAULT = ["helmet"]  # обязательные СИЗ вне зон по умолчанию (env; правится в UI «Настройки» → data/ppe_required.json)
REID_SIM_THRESHOLD = 0.55          # базовый порог (адаптивный 0.45–0.60)
REID_MAX_EMBEDDINGS = 30           # ракурсов на личность («со всех сторон»)
REID_MAX_AGE_DAYS = 0              # 0 = хранить личности бессрочно (авто-удаление выкл.)
REID_EMB_MAX_AGE_DAYS = 30         # TTL на эмбеддинг: ракурсы старше стираются, якорь жив (env, 0=выкл)
REID_EMB_CLEAN_INTERVAL = 3600     # период фонового состаривания эмбеддингов, сек (env)
REID_BODY_MAX_AGE_DAYS = 2         # короткий TTL дескрипторов тела (одежда устаревает), env, 0=выкл
REID_FLUSH_INTERVAL = 30           # период сброса выученного за сессию на диск, сек (env)
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

# NVR — непрерывная запись архива (по умолчанию выключена)
RECORD_ENABLED = False             # включить запись
RECORD_MODE = "motion"             # "motion" (только с движением) | "continuous" (24/7)
RECORD_DIR = "media"               # каталог архива (локальный диск)
RECORD_SEGMENT_SEC = 60            # длина сегмента, сек
RECORD_RETAIN_DAYS = 7             # хранить N дней
RECORD_MAX_DISK_PERCENT = 80       # чистить старейшее при занятости диска выше %
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
# NVR (опционально)
RECORD_ENABLED=true
RECORD_MODE=motion
RECORD_DIR=/media
RECORD_RETAIN_DAYS=7
# Требуемые СИЗ по умолчанию (вне зон). Для демо без каски/жилета:
PPE_REQUIRED_DEFAULT=mask        # нужна только маска (или пусто — СИЗ не нужны)
```

> 💡 **Демо/выставка:** проще всего отметить нужные СИЗ чекбоксами в «Настройки →
> Обязательные СИЗ для пропуска» (сохраняется в `data/ppe_required.json`, без рестарта).
> Альтернатива — env `PPE_REQUIRED_DEFAULT=mask` (или пустая строка — СИЗ не требуются
> нигде), либо в редакторе зон нарисовать зону с нужным набором `require_ppe`
> (внутри зоны действуют её требования).

> 🔊 **Голосовые предупреждения: основной синтез — на бэкенде (Piper TTS).**
> Речь тревог синтезируется на сервере фиксированным русским голосом Piper и
> отдаётся фронту готовым WAV (`GET /api/voice_alert_audio?text=...`) — качество
> не зависит от TTS-голосов ОС оператора. Мягкая деградация: если `piper-tts`/
> модель недоступны или `TTS_ENABLED=false`, эндпоинт отдаёт 503, и фронт
> откатывается на **Web Speech API** браузера. Web Speech требует русского
> TTS-голоса в ОС, иначе кириллицу читает английский голос «быстро и
> неразборчиво» → такая озвучка намеренно пропускается (в консоли —
> предупреждение `[voice] …русский голос ОС не найден`). Установить голос:
> - **Windows 11:** Параметры → Время и язык → Язык и регион → Русский →
>   ⋯ → Параметры языка → Речь → добавить речевой пакет (Microsoft Irina).
>   После этого перезапустить браузер.
> - **Linux:** установить `speech-dispatcher` + русский голос (`RHVoice`).
>
> Доставка алертов **курсорная** (`/api/voice_alert?after=<seq>`): клиент получает
> все новые алерты с момента подключения и проигрывает их последовательно,
> поэтому несколько вкладок и несколько камер работают независимо — алерт не
> «съедается» одним клиентом и не теряется при нескольких источниках. Голоса
> Web Speech в браузере подгружаются асинхронно — фронт ждёт `voiceschanged` и
> кэширует список, поэтому первый фоллбэк-алерт тоже звучит корректно.

> 🌐 **Офлайн-режим (без интернета).** Система рассчитана на работу в изолированной
> LAN. После однократной загрузки моделей (`python download_models.py` при наличии
> сети) интернет больше не нужен. При старте **без сети** загрузки моделей
> (InsightFace / OSNet body-Re-ID / Piper) **не блокируют запуск**: наличие сети
> проверяется быстрым коннектом, и при его отсутствии система сразу мягко
> деградирует (Re-ID и Body-Re-ID отключаются либо падают на цветовой дескриптор,
> озвучка идёт через Web Speech) — без зависаний на сетевых таймаутах.
> Обнаружение камер по LAN работает офлайн (сканируются подсети всех локальных
> интерфейсов хоста), локальные USB-камеры (числовой источник) — тоже без сети.

---

## 🗂️ Структура проекта

```
backend/
├── app.py                 # Flask entrypoint
├── config.py              # Константы
├── main.py                # Оркестратор (start/stop, потоки детекции, event-клипы)
├── recorder.py            # NVR: сегментная запись, индекс, retention
├── core/
│   ├── state.py           # DetectionState (треки, пропуска, логи, жесты)
│   ├── metrics.py         # MetricsRegistry (FPS, латентность, события)
│   └── models.py          # LogEntry
├── mqtt/
│   └── publisher.py       # MqttPublisher (события + HA discovery)
├── capture/
│   ├── buffer.py          # FrameBuffer
│   └── camera.py          # CameraCapture (RTSP/ffmpeg/local)
├── zones.py               # Полигональные зоны (danger/restricted/mask)
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
│   └── models.py          # Event, User, Camera, ApiKey, Recording
├── auth/
│   ├── routes.py          # login/refresh/me
│   └── service.py         # JWT, init_admin
└── api/
    ├── detection.py       # /start, /stop, /video_feed, /detect-modes, /upload
    ├── cameras.py         # CRUD камер + группы
    ├── reid.py            # Управление галереей лиц
    ├── events.py          # События: GET, clip, snapshot
    ├── monitoring.py      # /health, /metrics, /api/stats
    └── recordings.py      # NVR-архив: список/отдача сегментов

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
│   │   ├── ArchivePage.tsx # NVR-архив: таймлайн сегментов + плеер
│   │   ├── ZonesPage.tsx   # Редактор зон (SVG поверх кадра)
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
| `GET` | `/api/ppe-required` | Обязательные СИЗ для пропуска (helmet/mask/vest) |
| `PUT` | `/api/ppe-required` | Задать обязательные СИЗ (`{required:[...]}`) |
| `GET` | `/api/detection-settings` | Рантайм-настройки детекции: значения + спека (label/min/max/unit/group) |
| `PUT` | `/api/detection-settings` | Частичный патч настроек (`{settings:{key:val}}`), clamp на бэке |
| `GET` | `/api/voice_alert?after=<seq>` | Голосовые алерты новее курсора (`{alerts, cursor}`) |
| `GET` | `/api/voice_alert_audio?text=` | Синтез речи WAV (Piper); 503 → фоллбэк Web Speech |
| `GET` | `/api/notifications` | Очередь UI-уведомлений (жест ОК / нехватка СИЗ) |

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
| `POST` | `/api/cameras/discover` | Найти RTSP в сети (открытые + запароленные `status:locked`); `{add:true}` — автодобавить открытые |
| `POST` | `/api/cameras/discover/auth` | Добавить запароленную камеру по `{ip, username, password, port?, name?}` |
| `GET/PUT/POST` | `/api/cameras/<id>/zones` | Зоны камеры (получить/заменить/добавить) |
| `PUT/DELETE` | `/api/cameras/<id>/zones/<zid>` | Изменить/удалить зону |

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

### NVR / Архив
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/recordings` | Список сегментов (cam_id, from, to, пагинация) |
| `GET` | `/api/recordings/at?cam_id=&ts=` | Сегмент, покрывающий момент времени |
| `GET` | `/api/recordings/<id>` | Детали сегмента |
| `GET` | `/api/recordings/<id>/play` | Отдача mp4-сегмента (Range/перемотка) |

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

### 📹 USB-вебка у фронт-сервера (RTSP-рестрим)

Если фронт и бэк на разных серверах, а USB-вебку хочется держать у фронта —
поднимаем на фронт-сервере MediaMTX, он публикует вебку как RTSP, а бэк
забирает поток по сети (захват и детекция всегда на бэке):

```bash
# на фронт-сервере (вебка в /dev/video0)
docker compose -f docker-compose.frontend.yml --profile webcam up -d mediamtx
```

Затем в интерфейсе добавляем камеру с источником `rtsp://<FRONTEND_HOST>:8554/webcam`.
Настройки низкой задержки (`ultrafast` + `zerolatency`, малый GOP, TCP) — в `mediamtx.yml`
(на LAN ~100–300 мс). Прямого «воткнуть в фронт без задержки» нет: детекция идёт на
бэке, поэтому минимальная задержка — это USB прямо в бэк-сервер.

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
