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
# Камеры
CAMERAS = {
    "cam1": "rtsp://admin:password@192.168.1.100:554/stream1",
    "cam2": "rtsp://admin:password@192.168.1.101:554/stream1",
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
```bash
# Проверить версию JetPack: dpkg -l | grep nvidia-l4t-core
# JetPack 5.1.x → r35.4.1, JetPack 6.0 → r36.3.0
docker build -t ppe-detection -f Dockerfile.jetson \
  --build-arg L4T_TAG=r35.4.1 .

docker run --network host --runtime nvidia -d --name ppe-detector ppe-detection
```

> `--network host` обязателен для доступа к RTSP-камерам в локальной сети.
> На **Windows Docker Desktop** host-сеть недоступна — запускайте локально (`python app.py`).

#### Просмотр логов
```bash
docker logs -f ppe-detector
```

#### Остановка
```bash
docker stop ppe-detector && docker rm ppe-detector
```

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
├── Dockerfile
├── Dockerfile.jetson
```

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
