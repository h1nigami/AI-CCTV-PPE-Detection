from __future__ import annotations
import json
import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: list) -> list:
    val = os.environ.get(name)
    if val is None:
        return default
    return [x.strip() for x in val.split(",") if x.strip()]


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default

BASE_DIR = Path(__file__).parent.parent

MODEL_PATH = BASE_DIR / "models" / "best.pt"
POSE_MODEL_PATH = BASE_DIR / "models" / "yolov8n-pose.pt"
FACE_MODEL_PATH = BASE_DIR / "models" / "yolov8n-face.pt"
REID_MODEL_PATH = BASE_DIR / "models" / "yolov8n.pt"

CAMERAS: dict[str, str | int] = {"cam": 0}
CAMERAS_CONFIG: dict[str, dict] = {}

_CAMERAS_PATH = BASE_DIR / "data" / "cameras.json"
try:
    with open(_CAMERAS_PATH, encoding="utf-8") as _f:
        _loaded = json.load(_f)
        if isinstance(_loaded, dict) and _loaded:
            CAMERAS.clear()
            CAMERAS.update(_loaded)
except FileNotFoundError:
    _CAMERAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CAMERAS_PATH, "w", encoding="utf-8") as _f:
        json.dump(CAMERAS, _f, ensure_ascii=False, indent=2)

_CAMERAS_CONFIG_PATH = BASE_DIR / "data" / "cameras_config.json"
try:
    with open(_CAMERAS_CONFIG_PATH, encoding="utf-8") as _f:
        _loaded_cfg = json.load(_f)
        if isinstance(_loaded_cfg, dict):
            CAMERAS_CONFIG.update(_loaded_cfg)
except FileNotFoundError:
    pass


def save_cameras():
    with open(_CAMERAS_PATH, "w", encoding="utf-8") as _f:
        json.dump(CAMERAS, _f, ensure_ascii=False, indent=2)


def save_cameras_config():
    with open(_CAMERAS_CONFIG_PATH, "w", encoding="utf-8") as _f:
        json.dump(CAMERAS_CONFIG, _f, ensure_ascii=False, indent=2)


def get_camera_config(cam_id: str) -> dict:
    if cam_id not in CAMERAS_CONFIG:
        CAMERAS_CONFIG[cam_id] = {"detect_enabled": True}
        save_cameras_config()
    return CAMERAS_CONFIG[cam_id]


def set_camera_config(cam_id: str, **kwargs):
    if cam_id not in CAMERAS_CONFIG:
        CAMERAS_CONFIG[cam_id] = {}
    CAMERAS_CONFIG[cam_id].update(kwargs)
    save_cameras_config()

CONF_THRESH = 0.75
# Отдельный (более низкий) порог уверенности для ПРЕДМЕТОВ СИЗ — каска/маска/жилет.
# Они мельче человека и часто детектятся с уверенностью ниже CONF_THRESH(0.75);
# при едином пороге каска на голове нередко отбрасывалась ДО сопоставления с
# человеком → ложное «нет каски» (человек в каске получал голосовое предупреждение).
# Люди и конусы остаются на CONF_THRESH (чтобы не плодить ложные тела/зоны).
# Переопределяется env PPE_CONF_THRESH (ниже → больше каска ловится, но растёт риск
# ложного «СИЗ есть»; выше → строже). Не выше CONF_THRESH (иначе смысла нет).
PPE_CONF_THRESH = min(_env_float("PPE_CONF_THRESH", 0.5), CONF_THRESH)
MAX_LOG_SIZE = 100
# Если capture не пишет новых кадров дольше этого (сек) — камера считается
# «потерянной»: детекция перестаёт жечь GPU на застывшем кадре, а /video_frame
# отдаёт 204 → фронт показывает «NO SIGNAL» вместо замороженного кадра.
STREAM_STALE_SEC = 6.0

# Какие СИЗ обязательны ПО УМОЛЧАНИЮ (вне пользовательских зон и в зоне по
# конусам). Пер-зонные требования (`require_ppe` зоны) переопределяют это для
# людей внутри зоны. Дефолт — только каска (на выставку берём каску); полный
# комплект или другой набор задаётся через env, например
# PPE_REQUIRED_DEFAULT=helmet,mask,vest или PPE_REQUIRED_DEFAULT="" (СИЗ не нужны).
PPE_REQUIRED_DEFAULT = [x for x in _env_list("PPE_REQUIRED_DEFAULT", ["helmet"])
                        if x in ("helmet", "mask", "vest")]
# Минимум 3 конуса: из 2 точек многоугольник вырождается в отрезок (нет площади),
# зона рисовалась бы линией, в которую невозможно «войти» (is_in_danger_zone
# всегда False). С 3+ конусами зона имеет площадь и человек по точке ног в ней
# корректно детектится.
MIN_CONES = 3
ZONE_EXPAND_PX = 20
TOP_RATIO = 0.4
HAND_CROP_RATIO = 0.25
DEFECT_DEPTH_MIN = 15
DEFECT_MIN = 1
DEFECT_MAX = 3
MIN_HAND_AREA = 500
APPROVAL_DURATION = 300
PERSON_ID_GRID = 50
GESTURE_DISPLAY_DURATION = 3
GESTURE_COOLDOWN = 3.0
# Троттлинг ДОРОГОГО pose-инференса жеста: на одну личность запускаем
# detect_ok_gesture не чаще раза в GESTURE_CHECK_INTERVAL сек (жест держится
# секундами, чаще проверять незачем). Без этого при толпе N людей = N pose-
# инференсов на КАЖДЫЙ кадр → просадка FPS.
GESTURE_CHECK_INTERVAL = 0.5

FONT_PATHS = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
    BASE_DIR / "fonts" / "DejaVuSans.ttf",
]
FONT_SIZE_SMALL = 14
FONT_SIZE_NORMAL = 18
FONT_SIZE_LARGE = 22

COLOR_GREEN = (0, 255, 0)
COLOR_ORANGE = (0, 165, 255)
COLOR_RED = (0, 0, 255)
COLOR_YELLOW = (0, 255, 255)
COLOR_GOLD = (0, 215, 255)
COLOR_WHITE = (255, 255, 255)

CLASS_NAMES = {
    0: "Каска",
    1: "Маска",
    2: "Без каски",
    3: "Без маски",
    4: "Без жилета",
    5: "Человек",
    6: "Конус безопасности",
    7: "Защитный жилет",
    8: "Техника",
    9: "Транспорт",
}

REID_SIM_THRESHOLD = 0.55
# «Со всех сторон»: храним до 30 РАЗНЫХ ракурсов лица на личность (раньше 5 —
# новые ракурсы вытесняли старые). Дубли одного кадра не копятся (см.
# REID_DIVERSITY_MAX_SIM и _append_embedding с защитой якоря).
REID_MAX_EMBEDDINGS = 30
# «Навсегда»: 0 (или меньше) отключает авто-удаление старых личностей.
REID_MAX_AGE_DAYS = 0
# Затухание памяти ПО ВРЕМЕНИ на уровне отдельных эмбеддингов: образ человека
# (якорный эмбеддинг + last_seen) сохраняется, а лишние ракурсы старше
# REID_EMB_MAX_AGE_DAYS дней постепенно стираются (TTL на эмбеддинг), вместо
# того чтобы вытесняться вслепую при переполнении буфера. Якорь (индекс 0)
# неприкосновенен. 0/отрицательное — затухание выключено (хранить бессрочно).
REID_EMB_MAX_AGE_DAYS = float(os.getenv("REID_EMB_MAX_AGE_DAYS", "30"))
# Как часто (сек) фоновый цикл состаривает эмбеддинги (запись на диск только
# при реальном удалении). По умолчанию раз в час.
REID_EMB_CLEAN_INTERVAL = float(os.getenv("REID_EMB_CLEAN_INTERVAL", "3600"))
# TTL дескрипторов ТЕЛА (Body Re-ID). Внешний вид завязан на одежду и устаревает
# быстро (день-два), поэтому срок жизни короче, чем у лиц, и без защиты якоря.
# Сохраняются на диск (flush), переживают перезапуск в пределах TTL.
REID_BODY_MAX_AGE_DAYS = float(os.getenv("REID_BODY_MAX_AGE_DAYS", "2"))
# Как часто (сек) фоновый цикл сбрасывает на диск выученное за сессию (липкие
# лица + дескрипторы тела) — flush пишет pickle только при реальных изменениях.
REID_FLUSH_INTERVAL = float(os.getenv("REID_FLUSH_INTERVAL", "30"))
REID_GALLERY_PATH = BASE_DIR / "data" / "face_gallery.pkl"
REID_DET_SIZE = (640, 640)
REID_FRAME_SKIP = 3
# Анти-замусоривание галереи: с одного трека добавляем эмбеддинг не чаще
# REID_STORE_INTERVAL сек и только при качестве >= REID_MIN_STORE_QUALITY,
# иначе один и тот же кадр (кэш детектора лиц) вытесняет эталонные эмбеддинги.
REID_MIN_STORE_QUALITY = 0.55
REID_STORE_INTERVAL = 1.5
# В галерею добавляем новый эмбеддинг, только если он достаточно ОТЛИЧАЕТСЯ от
# уже сохранённых (max косинус < этого порога) — копим разные ракурсы, а не
# почти-дубли. Так 30 слотов покрывают реальные повороты головы, а не один кадр.
REID_DIVERSITY_MAX_SIM = 0.92
# Насколько ниже порога регистрации «прилипает» текущая личность трека.
# Порог липкости = max(REID_STICKY_MIN, threshold_for(quality) - margin).
# Большой margin + низкий минимум удерживают личность за треком даже на слабо
# похожем ракурсе (один человек, sim 0.3-0.5), а разные люди (~0) переключаются.
REID_STICKY_MARGIN = 0.25
REID_STICKY_MIN = 0.28

# ── Body Re-ID (опознание «со спины» по внешнему виду) ─────────────────────
# Лицевой Re-ID (InsightFace) видит только фронтальные лица. Когда человек стоит
# спиной/в профиль, эмбеддинга лица нет, и личность держится лишь устойчивостью
# трека ByteTrack. Body Re-ID добавляет вторичный сигнал — дескриптор внешнего
# вида человека, одинаковый с лица и со спины.
# Используется КОНСЕРВАТИВНО: только чтобы ВОССТАНОВИТЬ личность для трека без
# лица и без уже назначенной личности (новый/переинициализированный трек);
# решение по лицу он никогда не перекрывает.
REID_BODY_ENABLED = True
# Основной бэкенд — глубокая Re-ID модель OSNet (ONNX, onnxruntime). Даёт
# семантический дескриптор личности (одежда+силуэт), устойчивый к ракурсу —
# в отличие от цветовых гистограмм, которые путали перёд/спину и людей в похожей
# одежде. Если модель/onnxruntime недоступны — мягкая деградация на цветовой
# дескриптор (HSV-гистограммы торса/ног), система продолжает работать.
REID_BODY_MODEL = "osnet_x0_25_msmt17"
REID_BODY_MODEL_DIR = BASE_DIR / "models" / "osnet"
REID_BODY_MODEL_URL = (
    "https://huggingface.co/anriha/osnet_x0_25_msmt17/resolve/main/"
    "osnet_x0_25_msmt17.onnx"
)
# Размер входа OSNet (Ш×В) и фиксированный батч модели (anriha/osnet_x0_25_msmt17
# экспортирована со статическим батчем 16 → кропы людей гоняем пачками по 16).
REID_BODY_INPUT_W = 128
REID_BODY_INPUT_H = 256
REID_BODY_ONNX_BATCH = 16
# Косинусный порог повторного опознания трека по телу — для глубокого дескриптора.
# OSNet: один человек межкадрово ~0.5-0.9, разные люди обычно <0.4. Подбирать вживую.
REID_BODY_MATCH_THRESHOLD = 0.60
REID_BODY_DIVERSITY_MAX_SIM = 0.90
# Пороги для цветового fallback (дескриптор слабее → строже, чтобы не слить людей).
REID_BODY_MATCH_THRESHOLD_COLOR = 0.82
REID_BODY_DIVERSITY_MAX_SIM_COLOR = 0.97
# Сколько ракурсов тела храним на личность.
REID_BODY_MAX_EMBEDDINGS = 12
# Троттлинг записи дескриптора тела с одного трека (сек).
REID_BODY_STORE_INTERVAL = 1.0
# Минимальная площадь bbox человека (px²), ниже — дескриптор ненадёжен (далеко/мелко).
REID_BODY_MIN_AREA = 4000

# ── MinIO / Event Storage ─────────────────────────────────
MINIO_ENDPOINT = "minio:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET_EVENTS = "events"
MINIO_PUBLIC_URL = "http://localhost:9000"

# ── Event Recording ────────────────────────────────────────
EVENT_CLIP_FPS = 10
EVENT_PRE_FRAMES = 30
EVENT_POST_FRAMES = 30
EVENT_MAX_FRAMES = 300
VIOLATION_LOGS_DIR = BASE_DIR / "violation_logs"

# ── NVR: непрерывная (сегментная) запись архива ───────────
# Полноценный видеорегистратор: ffmpeg режет RTSP-поток на сегменты (`-c copy`,
# почти без CPU) на локальный диск; индекс сегментов — в БД (таблица Recording);
# фоновый чистильщик удаляет старое по сроку и при переполнении диска.
# По умолчанию ВЫКЛЮЧЕНО. См. backend/recorder.py.
RECORD_ENABLED = _env_bool("RECORD_ENABLED", False)
# Режим: "continuous" — писать всё 24/7; "motion" — хранить только сегменты с
# движением/событием (остальные чистильщик удаляет; экономия 80-90% диска).
RECORD_MODE = os.environ.get("RECORD_MODE", "motion")
RECORD_DIR = Path(os.environ.get("RECORD_DIR", str(BASE_DIR / "media")))
RECORD_SEGMENT_SEC = int(os.environ.get("RECORD_SEGMENT_SEC", "60"))  # длина сегмента
RECORD_RETAIN_DAYS = float(os.environ.get("RECORD_RETAIN_DAYS", "7"))  # хранить N дней
# Чистить старейшие сегменты, пока занятость диска под RECORD_DIR выше порога (%).
RECORD_MAX_DISK_PERCENT = float(os.environ.get("RECORD_MAX_DISK_PERCENT", "80"))
RECORD_CLEAN_INTERVAL_SEC = int(os.environ.get("RECORD_CLEAN_INTERVAL_SEC", "300"))
# В режиме "motion": сколько секунд держать сегмент без движения, прежде чем
# чистильщик его удалит (грейс на случай, если движение чуть за границей сегмента).
RECORD_MOTION_GRACE_SEC = int(os.environ.get("RECORD_MOTION_GRACE_SEC", "120"))

# ── Голосовые предупреждения ──────────────────────────────
# Минимальный интервал между предупреждениями на одну камеру (секунды).
VOICE_ALERT_COOLDOWN = 15.0

# ── Бэкенд-синтез речи (Piper TTS) ─────────────────────────
# Речь для тревог синтезируется на сервере (Piper) и отдаётся фронту готовым
# WAV — качество не зависит от TTS-голосов ОС оператора. Мягко деградирует:
# нет piper/модели → эндпоинт отдаёт 503, фронт откатывается на Web Speech
# (см. backend/tts/). Модель скачивается в рантайме в TTS_MODEL_DIR.
TTS_ENABLED = _env_bool("TTS_ENABLED", True)
TTS_MODEL = os.environ.get("TTS_MODEL", "ru_RU-irina-medium")
TTS_MODEL_DIR = os.environ.get("TTS_MODEL_DIR", str(BASE_DIR / "models" / "piper"))
TTS_CACHE_SIZE = int(os.environ.get("TTS_CACHE_SIZE", "64"))

# ── Motion detection (MOG2) перед YOLO ────────────────────
# «Motion First»: тяжёлая YOLO-детекция прогоняется только по кадрам с движением,
# на статичной сцене экономится 80-90% CPU/GPU. По умолчанию ВЫКЛЮЧЕНО — включение
# меняет поведение (пока нет движения, детекция/логи не обновляются). Включать на
# статичных сценах (RTSP с фиксированных камер). Параметры — см. backend/detection/motion.py.
MOTION_DETECTION_ENABLED = _env_bool("MOTION_DETECTION_ENABLED", False)
MOTION_THRESHOLD = 30        # порог бинаризации маски переднего плана (0..255)
MOTION_MIN_AREA = 1500       # минимальная площадь контура движения (px²)
MOTION_COOLDOWN_FRAMES = 15  # сколько кадров после спада движения ещё детектить

# ── MQTT (шина событий + Home Assistant) ──────────────────
# Публикация детекций/нарушений/heartbeat в MQTT-брокер (eclipse-mosquitto из
# docker-compose). По умолчанию ВЫКЛЮЧЕНО; деградирует мягко (нет paho/брокера —
# no-op). Реализация — backend/mqtt/publisher.py.
MQTT_ENABLED = _env_bool("MQTT_ENABLED", False)
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_TOPIC_PREFIX = os.environ.get("MQTT_TOPIC_PREFIX", "frigate")
MQTT_HA_DISCOVERY = _env_bool("MQTT_HA_DISCOVERY", False)  # Home Assistant MQTT discovery
# Минимальный интервал heartbeat в MQTT (сек).
MQTT_HEARTBEAT_INTERVAL = 30.0

# ── Автообнаружение камер (ONVIF + скан подсети) ──────────
# Поиск непаролёных RTSP-потоков в локальной сети. Кнопка «Найти камеры» в UI
# доступна всегда; CAMERA_AUTODISCOVER=true дополнительно запускает поиск и
# авто-добавление при старте сервера (по умолчанию выкл.). В Docker для ONVIF
# (multicast) нужен network_mode: host. См. backend/discovery.py.
CAMERA_AUTODISCOVER = _env_bool("CAMERA_AUTODISCOVER", False)
DISCOVERY_USE_ONVIF = _env_bool("DISCOVERY_USE_ONVIF", True)
DISCOVERY_USE_SCAN = _env_bool("DISCOVERY_USE_SCAN", True)
DISCOVERY_ONVIF_TIMEOUT = float(os.environ.get("DISCOVERY_ONVIF_TIMEOUT", "3"))
# Подсети для скана (через запятую): 'a.b.c', 'a.b.c.0/24' и т.п. — берутся
# первые три октета. Нужно в Docker bridge, где local_ip() = docker-адрес, а не
# LAN с камерами. К ним добавляются подсети уже добавленных камер (автоинференс).
DISCOVERY_SUBNET = os.environ.get("DISCOVERY_SUBNET", "")

# ── Глобальные режимы детекции ────────────────────────────
DETECT_MODES: dict[str, bool] = {
    "people": True,
    "ppe": True,
    "faces": True,
}

_DETECT_MODES_PATH = BASE_DIR / "data" / "detect_modes.json"
try:
    with open(_DETECT_MODES_PATH, encoding="utf-8") as _f:
        _loaded_modes = json.load(_f)
        if isinstance(_loaded_modes, dict):
            DETECT_MODES.update({k: bool(v) for k, v in _loaded_modes.items() if k in DETECT_MODES})
except FileNotFoundError:
    pass


def save_detect_modes():
    _DETECT_MODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_DETECT_MODES_PATH, "w", encoding="utf-8") as _f:
        json.dump(DETECT_MODES, _f, ensure_ascii=False, indent=2)


# ── Обязательные СИЗ для пропуска по жесту «ОК» (рантайм-настройка из UI) ──
# Персистится в data/ppe_required.json и ПЕРЕОПРЕДЕЛЯЕТ дефолт из env при старте.
# Мутируется ТОЛЬКО на месте (PPE_REQUIRED_DEFAULT[:] = ...), т.к. список
# импортирован по значению в main.py — переприсваивание разорвало бы связь.
_PPE_REQUIRED_PATH = BASE_DIR / "data" / "ppe_required.json"
try:
    with open(_PPE_REQUIRED_PATH, encoding="utf-8") as _f:
        _loaded_ppe = json.load(_f)
        if isinstance(_loaded_ppe, list):
            PPE_REQUIRED_DEFAULT[:] = [x for x in ("helmet", "mask", "vest")
                                      if x in _loaded_ppe]
except FileNotFoundError:
    pass


def save_ppe_required():
    _PPE_REQUIRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_PPE_REQUIRED_PATH, "w", encoding="utf-8") as _f:
        json.dump(PPE_REQUIRED_DEFAULT, _f, ensure_ascii=False, indent=2)
