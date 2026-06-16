# 👷 AI CCTV PPE Detection System

**Система видеоаналитики реального времени** для контроля средств индивидуальной защиты (СИЗ) на основе YOLOv8 и Flask. Детектирует людей, каски, маски, жилеты, опасные зоны и распознаёт жесты для управления доступом.

---

## 🚀 Возможности

- **Живой стрим** — подключение к RTSP/IP камерам, детекция СИЗ в реальном времени
- **Опасные зоны** — автоматическое построение зон по расположению конусов безопасности
- **Re-ID лиц** — кросс-камерная идентификация через InsightFace (buffalo_l) с русскими именами, адаптивный порог матчинга (quality-based), UI управления галереей
- **ByteTrack** — трекинг людей между кадрами (persistent track IDs), имена не перескакивают между людьми
- **Жест ОК** — распознавание жеста для выдачи пропуска в зону
- **Обработка файлов** — загрузка и анализ изображений и видео
- **Логирование** — история событий с временными метками и категориями
- **Уведомления** — всплывающие оповещения в браузере о пропусках (ЖЕСТ-ОК) и нарушениях СИЗ; имя человека подставляется из сообщения лога
- **Экспорт** — выгрузка логов в CSV
- **Печать** — отправка кадра с информацией о СИЗ на принтер

---

## 🛠️ Технологии

- **Backend**: Python 3.11+, Flask, OpenCV, Ultralytics YOLOv8
- **Frontend**: Vite 6 + React 19 + TypeScript
- **Re-ID**: InsightFace (buffalo_l) + ONNX Runtime
- **Детекция поз**: YOLOv8n-pose (распознавание жестов)
- **Визуализация**: PIL/Pillow (кириллица на кадре)
- **Сервер**: Waitress (production WSGI)
- **Контейнеризация**: Docker (CPU / GPU / Jetson) + docker compose

---

## 📦 Установка

### 1. Клонировать репозиторий
```bash
git clone https://github.com/your-username/AI-CCTV-PPE-Detection.git
cd AI-CCTV-PPE-Detection
```

### 2. Установить зависимости
```bash
pip install -r requirements.txt
```

### 3. Положить модель
```
models/
└── best.pt   ← обученная YOLOv8 модель
```

---

## ⚙️ Конфигурация

Все настройки в `config.py`:

```python
# Камеры: RTSP URL или число — индекс локальной камеры (/dev/videoN)
CAMERAS = {
    "cam1": "rtsp://admin:password@192.168.1.100:554/stream1",
    "usb": 0,  # /dev/video0
}

# Порог уверенности детекции
CONF_THRESH = 0.75

# Пропуск действует N секунд после жеста ОК
APPROVAL_DURATION = 300

# Re-ID (распознавание лиц)
REID_SIM_THRESHOLD = 0.55        # базовый порог (адаптивный: 0.48-0.72 в зависимости от качества лица)
REID_MAX_EMBEDDINGS = 5          # макс. эмбеддингов на личность
REID_MAX_AGE_DAYS = 30           # авто-чистка старых записей
REID_GALLERY_PATH = BASE_DIR / "data/face_gallery.pkl"
REID_FRAME_SKIP = 3              # запускать рекогнайшн каждый N-й кадр

```

---

## 🖥️ Запуск

### Локально
```bash
python app.py
```
Открыть в браузере: `http://localhost:8000`

### Docker

#### Быстрый старт (CPU)
```bash
docker compose --profile cpu up -d
```
Открыть в браузере: `http://localhost:8000`

#### GPU (NVIDIA CUDA)
```bash
docker compose --profile gpu up -d
```

#### Разработка (hot-reload кода)
```bash
docker compose --profile cpu -f docker-compose.yml -f docker-compose.override.yml up -d
```

#### Ручная сборка (CPU)
```bash
docker build -t ppe-detection:cpu -f Dockerfile .
docker run -d --name ppe-detector -p 8000:8000 ppe-detection:cpu
```

#### Ручная сборка (GPU)
```bash
docker build -t ppe-detection:gpu -f Dockerfile.gpu .
docker run -d --gpus all --name ppe-detector -p 8000:8000 ppe-detection:gpu
```

#### ARM64 + GPU (NVIDIA Jetson)

**Сборка:**
```bash
# Проверить версию JetPack: dpkg -l | grep nvidia-l4t-core
# JetPack 6.x → r36.4.0
docker build --network host \
  --build-arg L4T_TAG=r36.4.0 \
  -t ppe-detection -f Dockerfile.jetson .
```

**Запуск:**
```bash
docker rm -f ppe-detection 2>/dev/null
docker run -d --name ppe-detection \
  --network host \
  --runtime nvidia \
  --device /dev/video0:/dev/video0 \
  --device /dev/video1:/dev/video1 \
  ppe-detection
```

> `--network host` — обязателен для доступа к RTSP-камерам в локальной сети.
> `--runtime nvidia` — включает GPU (CUDA) на Jetson.
> `--device /dev/videoN` — пробрасывает USB/CSI-камеру в контейнер.
> На **Windows Docker Desktop** host-сеть недоступна — запускайте локально (`python app.py`).

#### Остановка
```bash
docker compose --profile cpu down
# или
docker compose --profile gpu down
```

#### Обслуживание на Jetson
```bash
docker container prune -f
docker image prune -af
docker buildx prune -af
```

---

### 🔧 Особенности сборки на Jetson

| Проблема | Решение |
|---|---|
| `Errno -2 Name or service not known` при pip install | `PIP_INDEX_URL="https://pypi.org/simple"` (образ `dustynv/l4t-pytorch` по умолчанию использует `jetson.webredirect.org`, который не резолвится внутри build-контейнера) |
| `Cannot uninstall blinker 1.4` (distutils) | `pip install --ignore-installed blinker==1.9.0` перед установкой Flask |
| `NumPy ABI mismatch` — torch собран с numpy 1.x | Отдельный `RUN pip install "numpy<2"` после основных пакетов |
| `ffmpeg: not found` | `apt-get install ffmpeg` |
| `The "timeout" option is deprecated` — ffmpeg на L4T трактует `-timeout` как listen-режим | Замена на `-stimeout` в `camera.py` |
| `python: executable file not found` | `CMD ["python3", ...]` вместо `python` |
| USB-вебкамера не открывается через `cv2.VideoCapture` на Jetson | OpenCV на L4T несовместим с V4L2 для UVC-устройств. Автоматический fallback на `ffmpeg -f v4l2` в `camera.py:_loop_opencv` |
| В контейнере нет `/dev/video0` | Пробросить устройство: `--device /dev/video0:/dev/video0` |

---

## 🗂️ Структура проекта

```
AI-CCTV-PPE-Detection/
│
├── backend/                # 🔧 Clean code архитектура
│   ├── app.py              #   Flask + регистрация роутов
│   ├── config.py           #   Константы
│   ├── main.py             #   Оркестратор (start/stop, process_frame)
│   ├── core/
│   │   ├── state.py        #   DetectionState (треки, пропуска, логи, жесты)
│   │   └── models.py       #   LogEntry
│   ├── capture/
│   │   ├── buffer.py       #   FrameBuffer
│   │   └── camera.py       #   CameraCapture (RTSP/ffmpeg/local)
│   ├── detection/
│   │   └── engine.py       #   run_detection, has_item_on_person, danger_zone
│   ├── gestures/
│   │   └── detector.py     #   detect_ok_gesture, detect_raised_hand
│   ├── reid/
│   │   ├── gallery.py      #   FaceGallery
│   │   ├── recognizer.py   #   FaceRecognizer + FaceRecognitionWorker
│   │   └── worker.py       #   FaceDetector (YOLO face)
│   ├── visualization/
│   │   └── renderer.py     #   put_text, draw_person, draw_legend...
│   └── api/
│       ├── detection.py    #   /start, /stop, /video_feed, /upload, /logs
│       ├── cameras.py      #   CRUD камер
│       └── reid.py         #   Управление галереей лиц
│
├── app.py                  # 📄 Тонкий реэкспорт → backend.app
├── config.py               # 📄 Тонкий реэкспорт → backend.config
├── main.py                 # 📄 Тонкий реэкспорт → backend.main
├── state.py                # 📄 Тонкий реэкспорт → backend.core.state
├── reid.py                 # 📄 Тонкий реэкспорт → backend.reid
├── camera.py               # 📄 Тонкий реэкспорт → backend.capture
├── detection.py            # 📄 Тонкий реэкспорт → backend.detection
├── gestures.py             # 📄 Тонкий реэкспорт → backend.gestures
├── visualization.py        # 📄 Тонкий реэкспорт → backend.visualization
│
├── frontend/               # 🌐 Vite + React + TypeScript
│   ├── src/
│   ├── public/
│   ├── dist/               # сборка для production
│   ├── package.json
│   └── vite.config.ts
│
├── models/
│   ├── best.pt
│   ├── yolov8n-pose.pt
│   └── yolov8n-face.pt
├── data/
│   ├── cameras.json        # конфигурация камер (RTSP URL)
│   └── face_gallery.pkl    # галерея лиц Re-ID (авто)
├── templates/
│   └── index.html          # fallback для старого фронтенда
├── uploads/
├── requirements.txt
├── Dockerfile              # CPU multi-stage
├── Dockerfile.gpu          # GPU (CUDA 12.4)
├── Dockerfile.jetson       # ARM64 + GPU (NVIDIA Jetson)
├── docker-compose.yml      # docker compose (cpu/gpu профили + MQTT)
├── docker-compose.override.yml  # dev hot-reload
└── PLAN.md                 # Дорожная карта трансформации
```

---

---

## 🔧 Производительность

- **Последовательная детекция** — камеры обрабатываются по одной в цикле, а не параллельно (4 потока перегружали CPU Jetson до 221%)
- **Polling JPEG** — `/video_frame/<cam_id>` отдаёт одиночный JPEG, фронтенд опрашивает каждые 100мс (10 FPS). Настраивается через `POLL_INTERVAL` в `index.html`.
- **Счётчик людей на камере** — каждая видео-ячейка отображает количество обнаруженных людей под камерой (бейдж `<div class="cam-counter">`)
- **FFmpeg PID cleanup** — при переподключении к RTSP старый процесс ffmpeg корректно завершается (`_stop_ffmpeg` в `camera.py`)
- **Re-ID (лица)** — распознавание запускается каждый `REID_FRAME_SKIP` (по умолч. 3) кадр для снижения нагрузки на GPU. Порог матчинга адаптивный: 0.48 для качественных лиц, до 0.72 для размытых/мелких
- **ByteTrack** — YOLO запускается с `model.track(persist=True)` вместо `model()`. Каждому человеку присваивается стабильный `track_id`, что исключает перескакивание имён между людьми при появлении/уходе из кадра. Старые треки очищаются через 60с бездействия
- **FFmpeg fallback** — если `ffmpeg` не найден в системе, RTSP читается через `cv2.VideoCapture(rtsp://...)` вместо падения с ошибкой
- **CPU на Jetson** — ~50-60% при 3-4 активных камерах, против 221% с параллельными потоками
- **GPU (CUDA)** — детекция YOLO на Jetson работает через CUDA (флаг `--runtime nvidia`). Без GPU используется CPU (~1-2 FPS)
- **Цикл детекции** — `time.sleep(0.05)` между итерациями вместо 1с, что убирает искусственное ограничение до 1 FPS

---

## 🎯 Логика работы

```
Камера (RTSP / USB)
    │
    ▼
CameraCapture → FrameBuffer
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
detection_worker          generate_live_feed
(лог, пропуска)           (видео + визуализация)
        │
        ▼
   ┌────┴────┐
   │         │
   ▼         ▼
Детекция   Re-ID (InsightFace)
СИЗ, зона  матчинг лиц → global_id
жест ОК    русское имя на кадре
   │         │
   └────┬────┘
        ▼
   Пропуск / Нарушение
```

### Статусы людей

| Цвет рамки | Статус |
|---|---|
| 🟢 Зелёный | Все СИЗ, вне зоны |
| 🟠 Оранжевый | В зоне, СИЗ есть |
| 🔴 Красный | В зоне, нарушение СИЗ |
| 🟡 Жёлтый | Вне зоны, нет СИЗ |
| 🟤 Золотой | Пропуск выдан |

---

## 📋 Формат логов

```json
{
  "id": "1717839045.123",
  "timestamp": "14:30:45",
  "message": "Людей: 2 | Александр: Вне зоны | Все СИЗ на месте",
  "category": "норма",
  "cam_id": "cam1",
  "global_id": 42
}
```

Категории: `норма` / `внимание` / `нарушение`

Сообщение лога парсится на фронтенде для извлечения имени человека. Формат части сообщения:
```
<имя> [<СИЗ>]: <статус>
```
Статус может быть: `ПРОПУСК`, `ОПАСНАЯ ЗОНА`, `Вне зоны`, `ЖЕСТ-ОК`. Если статус содержит `ЖЕСТ-ОК`, браузер показывает всплывающее уведомление.

---

## 🔁 API Re-ID (управление галереей лиц)

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/reid/persons` | Список всех личностей (ID, имя, камеры, кол-во эмбеддингов) |
| `POST` | `/api/reid/persons/<id>/rename` | Переименовать личность `{"name": "Сергей"}` |
| `DELETE` | `/api/reid/persons/<id>` | Удалить личность по global_id |
| `POST` | `/api/reid/clear` | Очистить всю галерею |
| `GET` | `/api/reid/stats` | Статистика (всего личностей, пропусков) |

Каждому новому лицу автоматически присваивается случайное русское имя.
Имена можно переименовывать через UI (кнопка "👤 Управление лицами" в левой панели) или через API.

---

## 📄 Лицензия

MIT © 2026

---

## 🔗 Ссылки

- [Ultralytics YOLOv8](https://docs.ultralytics.com/)
- [Flask](https://flask.palletsprojects.com/)
- [OpenCV](https://opencv.org/)
