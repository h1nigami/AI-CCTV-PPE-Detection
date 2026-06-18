# План трансформации AI-CCTV-PPE-Detection в платформу типа Frigate

## Текущее состояние (что уже работает)

- ✅ Многопоточный захват камер (RTSP, локальные, GStreamer, ffmpeg)
- ✅ YOLO детекция СИЗ (каска, маска, жилет) + трекинг (ByteTrack)
- ✅ Распознавание лиц (InsightFace / Re-ID) с кросс-камерной идентификацией
- ✅ Детекция жестов (OK жест, поднятые руки)
- ✅ Опасные зоны (на основе конусов безопасности)
- ✅ Flask Web UI с панелью статистики, логами, галереей лиц
- ✅ REST API (камеры, логи, Re-ID, загрузка файлов)
- ✅ Dockerfile (multi-stage с frontend сборкой)
- ✅ CSV экспорт логов
- ✅ Vite + React + TypeScript frontend (в процессе)
- ✅ CameraGrid с полноэкранным режимом (клик, Escape)
- ✅ Модальные окна: галерея лиц, управление камерами
- ✅ Уведомления о жестах OK / нарушениях
- ✅ Polling логов в реальном времени (1s)

---

## 1. Архитектура: Multiprocessing + MQTT

### Проблема
Сейчас всё работает в одном процессе с потоками (threading). При росте числа камер упираемся в GIL, нет изоляции ошибок.

### Цель
Перейти на многопроцессную архитектуру с MQTT для событий.

```
┌─────────────────────────────────────────────────────────────┐
│                      frigate                                 │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────┐ │
│  │ capture.py │  │ detect.py │  │ record.py │  │  api.py  │ │
│  │ (процесс)  │  │ (процесс) │  │ (процесс) │  │ (Flask)  │ │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └────┬─────┘ │
│        │              │              │              │        │
│        └──────────────┴──────────────┴──────────────┘        │
│                         │                                    │
│                    ┌────┴────┐                               │
│                    │  MQTT   │  (события: detection, motion, │
│                    │  Broker │   recording, heartbeat)       │
│                    └─────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

### Задачи
1. Разбить `main.py` на отдельные процессы:
   - `capture.py` — захват кадров (FrameBuffer → SharedMemory)
   - `detect.py` — детекция (SharedMemory → события в MQTT)
   - `record.py` — запись видео (MQTT-триггеры)
   - `api.py` — Flask/веб-интерфейс (только чтение из БД + MQTT publish)
2. Внедрить MQTT (Eclipse Mosquitto) для коммуникации между процессами
3. Использовать `multiprocessing.shared_memory` для передачи кадров (zero-copy
4)Добавить motion detection (OpenCV MOG2 / GMM) перед YOLO — запускать детекцию только при движении (экономия 80-90% CPU)

### Топики MQTT

```
frigate/cam1/motion        # движение обнаружено
frigate/cam1/detection     # человек/СИЗ обнаружены
frigate/cam1/violation     # нарушение
frigate/cam1/approved      # пропуск/допуск
frigate/cam1/record/start  # начать запись
frigate/cam1/record/stop   # остановить запись
frigate/system/heartbeat   # heartbeat процессов
frigate/system/health      # здоровье системы
```

---

## 2. Конфигурация: YAML-based (как Frigate config.yml)

### Проблема
Конфигурация размазана по `config.py`, `data/cameras.json`, жесткие константы в коде.

### Цель
Единый файл конфигурации с hot-reload.

### Пример config.yml

```yaml
mqtt:
  host: localhost
  port: 1883
  user: ""
  password: ""

cameras:
  main_entrance:
    rtsp: rtsp://user:pass@192.168.1.100:554/stream
    detect:
      width: 1280
      height: 720
      fps: 5
      min_confidence: 0.75
    motion:
      threshold: 30
      contour_area: 100
    zones:
      danger_zone:
        coordinates: [[100,100], [500,100], [500,400], [100,400]]
    record:
      enabled: true
      retain:
        days: 7
        mode: motion

detectors:
  cpu:
    type: cpu
    device: null
  coral:
    type: edgetpu
    device: usb

model:
  path: models/best.pt
  width: 640
  height: 640
  labels:
    0: "Каска"
    1: "Маска"
    2: "Без каски"
    3: "Без маски"
    4: "Без жилета"
    5: "Человек"
    6: "Конус безопасности"
    7: "Защитный жилет"
    8: "Техника"
    9: "Транспорт"

reid:
  enabled: true
  model: buffalo_l
  sim_threshold: 0.55
  max_embeddings: 5
  max_age_days: 30
  frame_skip: 3

gestures:
  ok_gesture: true
  raised_hand: true
  cooldown: 3.0

approval:
  duration: 300  # секунд
  zone_only: false  # только в опасной зоне

printer:
  name: "Argox OS-2130D PPLA"
  enabled: true

web:
  port: 8000
  host: 0.0.0.0
```

### Задачи
1. Установить зависимости: `pyyaml`, `pydantic`
2. Создать `config/schema.py` — Pydantic модели валидации
3. Создать `config/loader.py` — загрузка + hot-reload (watchdog / inotify)
4. Перенести все параметры из `config.py` в YAML
5. Удалить `data/cameras.json` — камеры теперь в YAML
6. Добавить `--config` аргумент в CLI

---

## 3. Запись видео (NVR функционал)

### Проблема
Видео не записывается, нет ретроспективы, нет возможности просмотреть нарушение в прошлом.

### Цель
Полноценный NVR с сегментированной записью, retention политиками, пребуфером.

### Функционал

| Функция | Описание | Реализация |
|---------|----------|------------|
| 24/7 запись | Круглосуточная запись всех камер | Segmented MP4 (1-5 мин сегменты) |
| Motion-only запись | Только при движении/детекции | Экономия места 80-90% |
| Event-only запись | Только при нарушении/жесте/человеке | Максимальная экономия |
| Пребуфер | 10 секунд до события | Ring buffer в RAM на 300 кадров |
| Retention | Ограничение по дням / размеру | Фоновый cleaner |
| Snapshots | JPG при событии | В БД + файловая система |
| RTSP рестриминг | Переупаковка RTSP для HA/VLC | ffmpeg -c copy -rtsp_transport tcp |
| WebRTC / MSE | < 500ms задержка live view | aiortc + MSE |

### Структура медиафайлов

```
/media/cam1/
  recordings/
    2026/
      06/
        15/
          cam1_12.00.00.mp4   (1 hour chunk)
          cam1_12.05.00.mp4
          ...
  clips/
    2026/
      06/
        15/
          cam1_1234567890.mp4  (event-based clip)
  snapshots/
    2026/
      06/
        15/
          cam1_1234567890.jpg
```

### Задачи
1. Создать `recorder.py` — отдельный процесс записи
2. Ring buffer в shared memory для пребуфера (300 кадров = 10 сек при 30fps)
3. Сегментированная запись через `cv2.VideoWriter` с `libx264`
4. Retention cleaner — проверка по дням и общий лимит диска (например, 80%)
5. Snapshot capture при событиях
6. API эндпоинты:
   - `GET /api/recordings?cam_id=...&date=...&time=...`
   - `GET /api/snapshots?cam_id=...&event_id=...`
   - `DELETE /api/recordings/cleanup`

### RTSP Рестриминг

```bash
ffmpeg -rtsp_transport tcp -i rtsp://... \
  -c copy -f rtsp rtsp://0.0.0.0:8554/cam1
```

Использовать `rtsp-simple-server` (v4l2loopback / MediaMTX) или встроенный встроить в Python через `aiortspy`.

---

## 4. Объектная модель событий (Events / Reviews)

### Проблема
Сейчас логи хранятся как строки в памяти (`state.py`), нет истории после перезапуска, нет поиска.

### Цель
Структурированные события в SQLite/PostgreSQL с быстрым поиском по камере, времени, типу, человеку.

### Схема БД

```sql
CREATE TABLE events (
    id          TEXT PRIMARY KEY,
    camera_id   TEXT NOT NULL,
    label       TEXT NOT NULL,        -- person, violation, approved, gesture
    sub_label   TEXT,                  -- no_helmet, no_mask, danger_zone
    timestamp   REAL NOT NULL,         -- unix timestamp
    start_time  REAL NOT NULL,
    end_time    REAL,
    has_clip    BOOLEAN DEFAULT 0,
    has_snapshot BOOLEAN DEFAULT 0,
    zones       TEXT,                   -- JSON array
    score       REAL,
    person_id   INTEGER,
    person_name TEXT,
    ppe_helmet  BOOLEAN,
    ppe_mask    BOOLEAN,
    ppe_vest    BOOLEAN,
    box_x       INTEGER,
    box_y       INTEGER,
    box_w       INTEGER,
    box_h       INTEGER
);

CREATE INDEX idx_events_camera_time ON events(camera_id, timestamp);
CREATE INDEX idx_events_label ON events(label);
CREATE INDEX idx_events_person ON events(person_id);
```

### Задачи
1. Выбрать БД: **SQLite** (минимализм) или **PostgreSQL** (масштабирование)
2. Создать `db.py` — адаптер для работы с events
3. Мигрировать `state.py` с LogEntry на события в БД
4. Добавить API:
   - `GET /api/events` — фильтры: camera, label, time_from, time_to, person
   - `GET /api/events/:id` — детали
   - `GET /api/events/stats` — агрегация (за день/неделю)
5. Review UI: timeline, фильтры, просмотр клипов/снимков

---

## 5. Зоны и маски

### Проблема
Сейчас опасная зона определяется по конусам — это негибко, нет визуального редактора.

### Цель
Полигональные зоны с визуальным редактором в Web UI, маски для исключения областей.

### Типы зон (как в Frigate)

| Тип | Описание |
|-----|----------|
| `danger` | Вход в зону = тревога (ваша опасная зона) |
| `restricted` | Только авторизованные могут входить |
| `required` | Объект должен быть в зоне для алерта |
| `mask` | Исключить область из детекции |

### Формат в YAML

```yaml
cameras:
  cam1:
    zones:
      danger_zone:
        type: danger
        coordinates: [[100,100], [500,100], [500,400], [100,400]]
        require_ppe: [helmet, mask, vest]
        alert_on_enter: true
      restricted_area:
        type: restricted
        coordinates: [[600,100], [900,100], [900,400], [600,400]]
        approved_persons_only: true
    motion:
      mask: [[0,0], [100,0], [100,100], [0,100]]  # исключить из motion
    detect:
      mask: [[0,0], [200,0], [200,200], [0,200]]   # исключить из детекции
```

### Задачи
1. Установить библиотеку `shapely` — операции с полигонами
2. Создать `zones.py` — модуль проверки вхождения в зону
3. Создать `masks.py` — наложение масок на кадр (cv2.fillPoly)
4. Визуальный редактор:
   - Canvas в Web UI (HTML5 Canvas)
   - Drag-and-drop точек полигона
   - Загрузка кадра как подложки
   - Сохранение в config.yml
   - Hot-reload конфигурации
5. API:
   - `GET /api/cameras/:id/zones`
   - `POST /api/cameras/:id/zones`
   - `PUT /api/cameras/:id/zones/:zone_id`
   - `DELETE /api/cameras/:id/zones/:zone_id`

---

## 6. Web UI: Next Level

### Проблема
Сейчас простой polling-стрим (JPEG каждые 100ms), базовая сетка, нет timeline.

### Цель
Современный дашборд с WebRTC/MSE стримингом, timeline скраббером, редактором зон.

### Функционал

| Функция | Текущий | Целевой |
|---------|---------|---------|
| Live view | Polling JPEG (100ms) | WebRTC / MSE live (<500ms) |
| Камеры | Фиксированная сетка | Адаптивная сетка + fullscreen + drag-drop |
| Timeline | Нет | Timeline скраббер с событиями |
| Синхронизация | Нет | Multi-camera sync play |
| События | Строковый список | Временная шкала + фильтры |
| Зоны | Нет редактора | Canvas редактор полигонов |
| Настройки | Нет в UI | Hot-reload настроек из UI |

### Технологии

**Вариант А (как Frigate):** Переписать frontend на TypeScript + Preact + Vite
- Плюсы: производительность, модульность, ecosystem
- Минусы: полная переписка frontend (2-3 недели)

**Вариант Б (эволюция):** Улучшить текущий vanilla JS шаг за шагом
- Плюсы: быстрее, можно итеративно
- Минусы: сложнее поддерживать сложную логику

### Рекомендация
Начать с Варианта Б (улучшить текущий UI), в перспективе перейти на Вариант А.

### Задачи для Web UI
1. **WebRTC live view:**
   - Установить `aiortc` (Python WebRTC)
   - Отдельный `webrtc.py` сигнальный сервер
   - JS WebRTC клиент (RTCPeerConnection)
   - MSE fallback для браузеров без WebRTC

2. **Timeline скраббер:**
   - Canvas-based timeline компонент
   - События отображаются как цветные полоски
   - Клик = переход к моменту
   - Zoom: 1h, 6h, 12h, 24h, custom range

3. **Zone/Mask редактор:**
   - Загрузка текущего кадра как background
   - Клик = добавление точки полигона
   - Drag точек = изменение формы
   - Сохранение в config.yml через API

4. **Multi-camera sync:**
   - Кнопка "Sync cameras"
   - Все камеры показывают один момент времени
   - Play/pause для синхронного просмотра

---

## 7. Детекторы (Multi-backend)

### Проблема
Сейчас только YOLO через Ultralytics (CUDA/CPU). Нет поддержки TPU, OpenVINO, TensorRT.

### Цель
Абстракция детектора с поддержкой различных бекендов.

### Архитектура

```python
class BaseDetector(ABC):
    @abstractmethod
    def detect(self, frame: np.ndarray) -> DetectionResult:
        pass

    @abstractmethod
    def load_model(self, path: str):
        pass

class YOLODetector(BaseDetector):
    # Текущий Ultralytics YOLO

class EdgeTPUDetector(BaseDetector):
    # Google Coral через tflite-runtime

class TensorRTDetector(BaseDetector):
    # NVIDIA TensorRT оптимизация

class OpenVINODetector(BaseDetector):
    # Intel OpenVINO
```

### Поддерживаемые бекенды

| Бекенд | Оборудование | Ускорение | Статус |
|--------|--------------|-----------|--------|
| Ultralytics CPU | Любой CPU | - | ✅ Есть |
| Ultralytics CUDA | NVIDIA GPU | 10-50x | ✅ Есть |
| TensorRT | NVIDIA GPU (Jetson/Desktop) | 2-5x над CUDA | ❌ Добавить |
| EdgeTPU | Google Coral USB/PCIe | 10-50x | ❌ Добавить |
| OpenVINO | Intel CPU/iGPU | 2-5x | ❌ Добавить |

### Задачи
1. Создать `detectors/__init__.py` + `base.py`
2. Мигрировать `detection.py` в `detectors/yolo.py`
3. Добавить `detectors/edgetpu.py`
4. Auto-detect доступного оборудования

---

## 8. Деплой: Docker Compose

### Проблема
Сейчас один Dockerfile со всем. Нет разделения сервисов, нет hardware passthrough.

### Цель
Docker Compose с раздельными сервисами, GPU/TPU passthrough, healthchecks.

### docker-compose.yml

```yaml
version: "3.9"

services:
  frigate-core:
    build: .
    privileged: true
    volumes:
      - ./config:/config
      - ./media:/media/frigate
      - /dev/bus/usb:/dev/bus/usb
      - /dev/dri:/dev/dri
    devices:
      - /dev/apex_0:/dev/apex_0
    environment:
      - TZ=Europe/Moscow
    restart: unless-stopped

  mqtt:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./mosquitto/config:/mosquitto/config
      - ./mosquitto/data:/mosquitto/data
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: frigate
      POSTGRES_USER: frigate
      POSTGRES_PASSWORD: frigate
    volumes:
      - ./pgdata:/var/lib/postgresql/data
    restart: unless-stopped

  web:
    image: nginx:alpine
    ports:
      - "8000:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - frigate-core
    restart: unless-stopped
```

### Задачи
1. Разделить Dockerfile на multi-stage build
2. Добавить docker-compose.yml
3. Настроить healthchecks для каждого сервиса
4. Добавить .env для конфиденциальных данных
5. Auto-restart on crash

---

## 9. Home Assistant Integration

### Цель
Интеграция с Home Assistant через MQTT discovery и custom component.

### Функционал

| Компонент HA | Топик MQTT |
|--------------|------------|
| Camera | `frigate/<camera>/snapshot` (JPEG) |
| Sensor: people count | `frigate/<camera>/people` |
| Sensor: violations | `frigate/<camera>/violations` |
| Binary sensor: motion | `frigate/<camera>/motion` |
| Binary sensor: danger zone | `frigate/<camera>/danger_zone` |
| Switch: record | `frigate/<camera>/record/set` |
| Switch: detection | `frigate/<camera>/detect/set` |

### MQTT Discovery

```json
// homeassistant/camera/frigate_cam1/config
{
  "name": "Frigate Cam1",
  "unique_id": "frigate_cam1",
  "topic": "frigate/cam1/snapshot",
  "device": {
    "identifiers": ["frigate"],
    "name": "Frigate PPE Detection",
    "model": "AI CCTV PPE",
    "manufacturer": "KONTROLER AI"
  }
}
```

### Задачи
1. Реализовать MQTT discovery publish при старте
2. Создать custom component для HA (или документировать ручную настройку)
3. Поддержка WebRTC в HA через `stream` компонент

---

## 10. Мониторинг и Observability

### Цель
Полная картина здоровья системы: FPS, latency, queue sizes, ошибки, метрики.

### Метрики

```
# Prometheus-style
frigate_detection_fps{camera="cam1"} 15
frigate_detection_latency_ms{camera="cam1"} 45
frigate_motion_fps{camera="cam1"} 30
frigate_events_total{camera="cam1",type="violation"} 42
frigate_queue_size{queue="detect"} 3
frigate_uptime_seconds 86400
frigate_memory_usage_mb 1200
frigate_cpu_percent 65
frigate_disk_usage_percent{mount="/media"} 45
```

### Задачи
1. ✅ Добавить `/api/stats` — JSON метрики (`backend/api/monitoring.py`)
2. Структурированное логирование (JSON, не print)
3. ✅ Healthcheck endpoint (`/health`)
4. ✅ Prometheus exporter (`/metrics`, `backend/core/metrics.py`)
5. Grafana dashboard (опционально, предоставить JSON шаблон)

---

## 🗺️ Roadmap

### Фаза 1: Архитектурная перестройка (MVP)
**Срок: 2-3 недели** — 🔴 Приоритет 1

- [ ] YAML конфигурация + парсер
- [x] MQTT брокер + клиент (брокер в docker-compose; клиент-публикатор `backend/mqtt/publisher.py`, опционален, мягкая деградация)
- [ ] Разделение на процессы: capture, detect, record, api
- [x] Motion detection (MOG2) перед YOLO (`backend/detection/motion.py`, гейт в `detection_loop`, конфиг `MOTION_*`)
- [ ] Shared memory для кадров (zero-copy)
- [ ] Базовая запись (24/7 segmented MP4)

### Фаза 2: NVR Core
**Срок: 2-3 недели** — 🔴 Приоритет 1

- [ ] Event-based запись (по триггеру)
- [ ] Retention policy cleaner
- [ ] Snapshot capture
- [ ] RTSP restream
- [ ] WebRTC live view (aiortc)
- [ ] API для медиафайлов

### Фаза 3: События и Review
**Срок: 2 недели** — 🟡 Приоритет 2

- [ ] SQLite/PostgreSQL events DB
- [ ] Миграция state.py → DB
- [ ] API эндпоинты для событий
- [ ] Timeline скраббер в UI
- [ ] Фильтры и поиск по событиям
- [ ] Экспорт клипов/снимков

### Фаза 4: Зоны и маски
**Срок: 1-2 недели** — 🟡 Приоритет 2

- [ ] Полигональные зоны (shapely)
- [ ] Маски детекции/motion
- [ ] Визуальный редактор в UI (Canvas)
- [ ] Hot-reload конфигурации

### Фаза 5: Multi-backend детекторы
**Срок: 1 неделя** — 🟢 Приоритет 3

- [ ] Абстрактный BaseDetector
- [ ] YOLO (current)
- [ ] EdgeTPU (Google Coral)
- [ ] TensorRT (NVIDIA)
- [ ] OpenVINO (Intel)
- [ ] Auto-detect оборудования

### Фаза 6: Экосистема
**Срок: 2 недели** — 🟢 Приоритет 3

- [x] Home Assistant MQTT discovery (`MqttPublisher._publish_discovery`, тумблер `MQTT_HA_DISCOVERY`)
- [ ] Custom component для HA
- [ ] Docker Compose (multi-service)
- [x] Prometheus метрики (`/metrics`, `backend/core/metrics.py`)
- [x] Healthchecks (`/health`)
- [ ] Документация (README, config reference)

### Фаза 7: UI Renaissance
**Срок: 2-3 недели** — 🟢 Приоритет 3

- [x] TypeScript + React + Vite frontend
- [x] Адаптивная сетка камер с полноэкранным режимом (клик ↔ fullscreen, Escape)
- [x] Левая панель: статус СИЗ, счётчики, люди в кадре
- [x] Правая панель: события (лог) в реальном времени
- [x] Уведомления при жесте OK / нарушении
- [x] Модальное окно управления галереей лиц
- [x] Модальное окно управления камерами (добавить/удалить/переименовать)
- [x] Vite proxy → Flask API (dev режим)
- [ ] Multi-camera синхронизация
- [ ] Drag-and-drop layout
- [ ] Светлая тема
- [ ] Keyboard shortcuts

---

## 📊 Итоговое сравнение

| Функция | Сейчас | После трансформации (как Frigate) |
|---------|--------|----------------------------------|
| Архитектура | Один процесс + threading | Multiprocess + MQTT |
| Детекция | YOLO (каждый кадр) | Motion-triggered YOLO |
| Конфиг | Python `.py` + JSON | YAML + hot-reload |
| Запись видео | ❌ Нет | 24/7 + event + retention |
| Live view | Polling JPEG (100ms) | WebRTC (<500ms) |
| Зоны | Только конусы | Полигоны + редактор + маски |
| События | LogEntry в памяти | SQLite/DB + поиск + timeline |
| Лица | InsightFace | InsightFace + gallery управление |
| Детекторы | Только CPU/CUDA | CPU + Coral + TensorRT + OpenVINO |
| БД | Data classes | SQLite / PostgreSQL |
| HA интеграция | ❌ Нет | MQTT discovery + custom component |
| RTSP restream | ❌ Нет | ffmpeg restream |
| Docker | Один контейнер | Docker Compose + hardware passthrough |
| Мониторинг | print() | Prometheus + JSON logs + healthchecks |
| Web UI | Vanilla JS + Flask templates | Vite + React + TypeScript + Canvas (в работе) |

---

## 🛠️ Технологический стек

### Текущий
- Python 3.11
- Flask + Waitress
- Ultralytics YOLO
- InsightFace
- OpenCV
- ByteTrack
- Docker

### Добавить
- **PyYAML** + **Pydantic** — конфигурация
- **Paho-MQTT** — MQTT клиент
- **Eclipse Mosquitto** — MQTT брокер
- **aiortc** — WebRTC
- **Shapely** — работа с полигонами
- **Alembic** — миграции БД (если PostgreSQL)
- **SQLite3** — встроенная БД (для малых инсталляций)
- **Prometheus Client** — метрики
- **Structured logging** (json) — вместо print()
- **MediaMTX / rtsp-simple-server** — RTSP restream
- **tflite-runtime** — EdgeTPU
- **Preact + Vite** — frontend (опционально)

---

## 💡 Ключевые архитектурные решения

### 1. MQTT — центральная шина
MQTT используется **вместо REST** для внутренней коммуникации процессов. Это дает:
- Слабое связывание компонентов
- Простое масштабирование
- Легкая интеграция с Home Assistant
- История событий через retained messages

### 2. Motion First, Detection Second
Типичный кадр не содержит движения. Motion detection (MOG2) занимает 1-2ms, YOLO — 20-100ms.
Пропуская статичные кадры, экономим 80-90% GPU/CPU ресурсов.

### 3. Shared Memory для Кадров
Кадры большие (1280x720x3 ≈ 2.7MB). Передача через pipe/сокеты медленная.
Используем `multiprocessing.shared_memory` (Python 3.8+) — zero-copy shared memory.

### 4. Ring Buffer для Пребуфера
Храним последние 300 кадров в памяти.
При срабатывании детекции — сохраняем 10 сек ДО события как часть клипа.

### 5. YAML как Source of Truth
Единый config.yml:
- Версионируется в git
- Легко редактировать
- Hot-reload
- Backup одной строкой

---

## 🚀 Коммерческая платформа: Продажа видеоаналитики

### Бизнес-модель
Продаём **доступ к видеоаналитике как сервис** (SaaS/on-prem). Клиент платит за:
- **Количество камер** (базовый тариф: 1-4 камеры, профи: 8+, enterprise: безлимит)
- **Функции** (базовый: детекция СИЗ, профи: +распознавание лиц, enterprise: +NVR запись)
- **Срок подписки** (месяц / год / 3 года со скидкой)
- **White-label брендинг** (для интеграторов)

### Целевые сегменты

| Сегмент | Проблема | Наше решение | Цена |
|---------|----------|-------------|------|
| **Стройки** | Контроль СИЗ на входе | Детекция каски/жилета + пропускная система | 5 000-15 000 ₽/мес |
| **Заводы/Цеха** | Опасные зоны, допуск персонала | Детекция + зоны + Re-ID лиц | 15 000-50 000 ₽/мес |
| **Складские комплексы** | Контроль периметра, техника безопасности | Детекция + запись + алерты | 20 000-60 000 ₽/мес |
| **Интеграторы** | White-label для своих клиентов | API + брендирование + техподдержка | Договорная |

### Технические требования для коммерции

#### 1. Мультитенантность (Multi-tenant)

```
┌─────────────────────────────────────────────────────────┐
│                    API Gateway                           │
├─────────────────────────────────────────────────────────┤
│  Tenant A         Tenant B         Tenant C              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐           │
│  │ admin    │    │ admin    │    │ admin    │           │
│  │ operator │    │ viewer   │    │ operator │           │
│  │ api-key  │    │ api-key  │    │ viewer   │           │
│  └──────────┘    └──────────┘    └──────────┘           │
│         │              │              │                  │
│         └──────────────┴──────────────┘                  │
│                         │                                │
│              ┌──────────┴──────────┐                     │
│              │   Shared Instance   │  (или выделенный)    │
│              │   или выделенный    │                     │
│              │   Docker контейнер  │                     │
│              └─────────────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

**Стратегия:**
- **Start small:** Один инстанс на всех клиентов, разделение по `tenant_id` в БД
- **Scale up:** Выделенный Docker-контейнер на каждого крупного клиента (изоляция)
- **Enterprise:** On-prem установка на сервере клиента

#### 2. API-ключи для продажи доступа (уже частично реализовано)

- ✅ Модель `ApiKey` в SQLAlchemy (`backend/db/models.py`)
- ✅ Middleware `@api_key_required` (`backend/auth/middleware.py`)
- ✅ JWT аутентификация (access + refresh tokens)
- ❌ Нет UI для управления ключами (создание, отзыв, лимиты)
- ❌ Нет rate limiting
- ❌ Нет привязки ключа к tenant'у
- ❌ Нет логирования использования ключа

#### 3. Биллинг и подписки

```
Тарифы:
┌──────────────┬──────────┬──────────┬────────────┐
│              │  Базовый │   Профи  │ Enterprise │
├──────────────┼──────────┼──────────┼────────────┤
│ Камеры       │  до 4    │  до 16   │ безлимит   │
│ Детекция СИЗ │  ✅      │  ✅      │ ✅         │
│ Опасные зоны │  ✅      │  ✅      │ ✅         │
│ Re-ID лиц    │  ❌      │  ✅      │ ✅         │
│ NVR запись   │  ❌      │  7 дней  │ 30 дней    │
│ API доступ   │  ❌      │  ✅      │ ✅         │
│ White-label  │  ❌      │  ❌      │ ✅         │
│ Поддержка    │  Email   │  Email   │ 24/7       │
│ Цена/мес     │  5 000₽  │ 15 000₽  │ договорная │
└──────────────┴──────────┴──────────┴────────────┘
```

**MVP биллинга:**
- Ручное создание подписок через админку (без интеграции с платежными системами)
- Позже: интеграция с ЮKassa / CloudPayments / Stripe
- Позже: автоматическое продление, инвойсы, напоминания

#### 4. Мониторинг использования (Usage Metering)

Что метрицировать для биллинга:
```sql
CREATE TABLE usage_metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT NOT NULL,
    camera_id    TEXT,
    metric_name  TEXT NOT NULL,  -- 'detection_hours', 'api_calls', 'storage_gb'
    value        REAL NOT NULL,
    recorded_at  TEXT NOT NULL   -- ISO datetime
);

-- Агрегированный отчёт для инвойса:
SELECT tenant_id, metric_name, SUM(value)
FROM usage_metrics
WHERE recorded_at BETWEEN ? AND ?
GROUP BY tenant_id, metric_name;
```

#### 5. Webhooks и интеграции (для продажи API-доступа)

```python
# webhooks.py — отправка событий на HTTP-эндпоинт клиента
@dataclass
class WebhookEvent:
    event_type: str       # violation, approved, motion, person_enter
    camera_id: str
    timestamp: str
    payload: dict         # снимок, bbox, СИЗ статус, имя человека

# Клиент регистрирует webhook:
POST /api/webhooks
{
    "url": "https://client-server.com/frigate-webhook",
    "events": ["violation", "approved"],
    "secret": "whsec_..."
}
```

#### 6. Админ-панель для управления клиентами

```
/админ
├── /dashboard     — сводка по всем клиентам (камеры, события, статус)
├── /tenants       — список тенантов
│   ├── /tenants/:id — детали: пользователи, камеры, подписка, биллинг
│   └── /tenants/:id/usage — графики использования
├── /plans         — управление тарифами
├── /invoices      — инвойсы и оплаты
└── /webhooks      — мониторинг доставки вебхуков
```

#### 7. White-label брендинг

```yaml
# config.yml — настройки брендинга для клиента
branding:
  company_name: "СтройБезопасность"
  logo_url: "https://client.com/logo.png"
  primary_color: "#2563eb"
  favicon_url: "https://client.com/favicon.ico"
  custom_domain: "analytics.stroybez.ru"  # кастомный домен
  hide_powered_by: true                    # убрать "Powered by Kontroler AI"
```

---

## 🗺️ Обновлённый Roadmap (с учётом коммерции)

### Фаза 0: Текущее состояние (DONE) ✅
- [x] Vite + React + TypeScript frontend
- [x] CameraGrid + CameraCard (MJPEG/polling)
- [x] DispatcherPanel (СИЗ, события, люди)
- [x] Header с навигацией и группами
- [x] Аутентификация (JWT + регистрация/логин)
- [x] SQLite + Alembic миграции
- [x] Docker build (cpu/gpu профили)
- [x] GalleryModal (управление лицами)

### Фаза 1: Продаваемый MVP (4-6 недель) 🚀
**Цель: выпустить продукт, который можно продавать**

#### 1.1 Мультитенантность (2 недели)
- [ ] `tenant_id` во все модели БД (User, Camera, Event, ApiKey)
- [ ] Регистрация с выбором тарифа (или ручное создание в админке)
- [ ] Изоляция данных: каждый пользователь видит только свои камеры
- [ ] API с tenant-scoped доступом
- [ ] Middleware проверки лимитов (кол-во камер по тарифу)

#### 1.2 API-ключи + UI (1 неделя)
- [ ] UI для создания/отзыва API-ключей
- [ ] Привязка ключа к tenant'у и роли
- [ ] Rate limiting (1000 req/min для базового, 10000 для профи)
- [ ] Логирование использования ключа (для биллинга)

#### 1.3 Админ-панель (2 недели)
- [ ] Dashboard: все клиенты, статус, события
- [ ] CRUD тенантов (создание, редактирование тарифа, блокировка)
- [ ] Просмотр использования (камеры, события, API calls)
- [ ] Управление подписками (ручное создание/продление)

#### 1.4 Webhooks (1 неделя)
- [ ] Регистрация webhook'ов через UI/API
- [ ] Доставка событий (с retry + exponential backoff)
- [ ] Лог доставки + dashboard статуса
- [ ] Подпись запросов (HMAC-SHA256)

#### 1.5 События в БД + API (1-2 недели)
- [ ] Запись событий детекции в SQLite (миграция из in-memory LogEntry)
- [ ] API: `GET /api/events` с фильтрацией (камера, тип, время, человек)
- [ ] API: `GET /api/events/stats` (агрегация для графиков)
- [ ] Экспорт событий (CSV/JSON)

### Фаза 2: NVR + Запись (3-4 недели)
- [ ] 24/7 сегментированная запись (MP4 сегменты по 1 мин)
- [ ] Event-triggered запись (пребуфер 10 сек)
- [ ] Snapshot capture при событиях
- [ ] API для просмотра записей
- [ ] Timeline в UI (просмотр архива)
- [ ] Retention policy (очистка старых записей)

### Фаза 3: Брендинг и упаковка (2 недели)
- [ ] White-label: логотип, цвета, домен
- [ ] Страница логина с брендом клиента
- [ ] Email-уведомления (нарушения, отчёты)
- [ ] Telegram-бот для алертов
- [ ] PDF-отчёты (смена, день, неделя)

### Фаза 4: Биллинг (3-4 недели)
- [ ] Интеграция с ЮKassa / CloudPayments
- [ ] Автоматическое создание подписки при регистрации
- [ ] Продление/отмена подписки
- [ ] Инвойсы (PDF на email)
- [ ] Пробный период (14 дней)
- [ ] Grace period при просрочке оплаты

### Фаза 5: Enterprise (ongoing)
- [ ] On-prem установка (Docker-образ для клиента)
- [ ] LDAP / SAML SSO
- [ ] Аудит-лог (все действия пользователей)
- [ ] High availability (кластеризация)
- [ ] SLA мониторинг (uptime, latency)
- [ ] Кастомные модели (обучение под объекты клиента)

---

## 📈 Ключевые метрики для коммерции

| Метрика | Где считать | Цель |
|---------|-------------|------|
| MRR (Monthly Recurring Revenue) | Биллинг | — |
| Churn rate | Подписки | < 5% |
| Камер на клиента | Usage | > 4 |
| Event detection latency | Система | < 200ms |
| API uptime | Мониторинг | > 99.9% |
| Среднее время инцидента | Поддержка | < 1 час (enterprise) |
| NPS | Опросы | > 50 |

---

## 🔐 Безопасность (для Enterprise-продаж)

- [ ] HTTPS everywhere (Let's Encrypt auto)
- [ ] Password hashing (bcrypt — уже есть)
- [ ] Rate limiting на /api/auth/login (защита от brute force)
- [ ] JWT refresh rotation
- [ ] API keys with scoped permissions
- [ ] Audit log всех изменений
- [ ] Data isolation между клиентами (tenant_id)
- [ ] GDPR compliance (экспорт/удаление данных клиента)
- [ ] Vulnerability scanning в CI/CD
