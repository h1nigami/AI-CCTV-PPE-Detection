# 👷 AI CCTV PPE Detection System

**Система видеоаналитики реального времени** для контроля средств индивидуальной защиты (СИЗ) на основе YOLOv8 и Flask. Детектирует людей, каски, маски, жилеты, опасные зоны и распознаёт жесты для управления доступом.

---

## 🚀 Возможности

- **Живой стрим** — подключение к RTSP/IP камерам, детекция СИЗ в реальном времени
- **Опасные зоны** — автоматическое построение зон по расположению конусов безопасности
- **Жест ОК** — распознавание жеста для выдачи пропуска в зону
- **Поднятая рука** — жест для запуска печати кадра на принтере
- **Обработка файлов** — загрузка и анализ изображений и видео
- **Логирование** — история событий с временными метками и категориями
- **Экспорт** — выгрузка логов в CSV
- **Печать** — отправка кадра с информацией о СИЗ на принтер

---

## 🛠️ Технологии

- **Backend**: Python 3.10+, Flask, OpenCV, Ultralytics YOLOv8
- **Детекция поз**: YOLOv8n-pose (распознавание жестов)
- **Визуализация**: PIL/Pillow (кириллица на кадре)
- **Сервер**: Waitress (production WSGI)
- **Печать**: win32print (Windows), CUPS (Linux)
- **Контейнеризация**: Docker

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

# Принтер (Windows)
PRINTER_NAME = "Argox OS-2130D PPLA"
```

---

## 🖥️ Запуск

### Локально
```bash
python app.py
```
Открыть в браузере: `http://localhost:8000`

### Docker

#### x86_64 (Windows / Linux)
```bash
docker build -t ppe-detection -f Dockerfile .
docker run -d --name ppe-detector -p 8000:8000 ppe-detection
```

#### ARM64 + GPU (NVIDIA Jetson)

**Сборка** (полная, с установкой зависимостей):
```bash
# Проверить версию JetPack: dpkg -l | grep nvidia-l4t-core
# JetPack 6.x → r36.4.0
docker build --network host \
  --build-arg L4T_TAG=r36.4.0 \
  -t ppe-detection -f Dockerfile.jetson .
```

**Быстрая пересборка** (только код приложения, кэш pip/apt):
```bash
# Создать временный Dockerfile
cat > Dockerfile.hotfix << 'EOF'
FROM ppe-detection:latest
COPY . /app/
EOF
docker build -t ppe-detection -f Dockerfile.hotfix .
rm Dockerfile.hotfix
```

**Запуск** (с GPU и USB-камерой):
```bash
docker rm -f ppe-detection 2>/dev/null
docker run -d --name ppe-detection \
  --network host \
  --runtime nvidia \
  --device /dev/video0:/dev/video0 \
  --device /dev/video1:/dev/video1 \
  ppe-detection
```

**Просмотр логов:**
```bash
docker logs -f ppe-detection
```

> `--network host` — обязателен для доступа к RTSP-камерам в локальной сети.
> `--runtime nvidia` — включает GPU (CUDA) на Jetson (без него YOLO работает на CPU, ~1 FPS).
> `--device /dev/videoN` — пробрасывает USB/CSI-камеру в контейнер.
> На **Windows Docker Desktop** host-сеть недоступна — запускайте локально (`python app.py`).

#### Просмотр логов
```bash
docker logs -f ppe-detection
```

#### Остановка
```bash
docker stop ppe-detection && docker rm ppe-detection
```

#### Обслуживание на Jetson

Очистка неиспользуемых образов и кэша сборки (экономит ~30+ ГБ):
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
├── app.py              # Flask роуты
├── main.py             # Точка сборки, detection worker, live feed
├── config.py           # Все константы и настройки
├── state.py            # Потокобезопасный стейт приложения
├── camera.py           # Захват кадров, буфер, автопереподключение
├── detection.py        # Логика СИЗ, опасных зон
├── gestures.py         # Распознавание жестов (ОК, поднятая рука)
├── visualization.py    # Отрисовка на кадре (PIL, кириллица)
├── printer.py          # Печать кадра на принтер
├── models/
│   └── best.pt
├── templates/
│   └── index.html
├── uploads/
├── requirements.txt
├── Dockerfile              # x86_64 (Windows / Linux)
├── Dockerfile.jetson       # ARM64 + GPU (NVIDIA Jetson)
```

---

---

## 🔧 Производительность

- **Последовательная детекция** — камеры обрабатываются по одной в цикле, а не параллельно (4 потока перегружали CPU Jetson до 221%)
- **Polling JPEG** — `/video_frame/<cam_id>` отдаёт одиночный JPEG, фронтенд опрашивает раз в 2с. Вместо `multipart/x-mixed-replace`, который блокировал пул Waitress
- **FFmpeg PID cleanup** — при переподключении к RTSP старый процесс ffmpeg корректно завершается (`_stop_ffmpeg` в `camera.py`)
- **CPU на Jetson** — ~50-60% при 3-4 активных камерах, против 221% с параллельными потоками
- **GPU (CUDA)** — детекция YOLO на Jetson работает через CUDA (флаг `--runtime nvidia`). Без GPU используется CPU (~1-2 FPS)
- **Цикл детекции** — `time.sleep(0.05)` между итерациями вместо 1с, что убирает искусственное ограничение до 1 FPS

---

## 🎯 Логика работы

```
Камера (RTSP)
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
   Детекция СИЗ
   Опасная зона (по конусам)
   Жест ОК → пропуск
   Поднятая рука → печать
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
  "message": "Людей: 2 | Чел.1: ОПАСНАЯ ЗОНА | Нет СИЗ: маска | Чел.2: Вне зоны | Все СИЗ на месте",
  "category": "нарушение",
  "cam_id": "cam1"
}
```

Категории: `норма` / `внимание` / `нарушение`

---

## 🖨️ Печать

Для печати на принтер при жесте "поднятая рука":

**Windows** — установить `pywin32`:
```bash
pip install pywin32
```

**Linux** — установить CUPS:
```bash
sudo apt install cups
```

Посмотреть доступные принтеры:
```python
import win32print
printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
for p in printers:
    print(p[2])
```

---

## 📄 Лицензия

MIT © 2026

---

## 🔗 Ссылки

- [Ultralytics YOLOv8](https://docs.ultralytics.com/)
- [Flask](https://flask.palletsprojects.com/)
- [OpenCV](https://opencv.org/)
