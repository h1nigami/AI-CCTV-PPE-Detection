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
MAX_LOG_SIZE = 100

# Какие СИЗ обязательны ПО УМОЛЧАНИЮ (вне пользовательских зон и в зоне по
# конусам). Пер-зонные требования (`require_ppe` зоны) переопределяют это для
# людей внутри зоны. Для демо/выставки можно ослабить через env, например
# PPE_REQUIRED_DEFAULT=mask (нужна только маска) или PPE_REQUIRED_DEFAULT=""
# (СИЗ не обязательны нигде — не нужно нести каску/жилет).
PPE_REQUIRED_DEFAULT = [x for x in _env_list("PPE_REQUIRED_DEFAULT", ["helmet", "mask", "vest"])
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

# ── Body Re-ID (опознание «со спины» по внешнему виду одежды/силуэта) ──────
# Лицевой Re-ID (InsightFace) видит только фронтальные лица. Когда человек стоит
# спиной/в профиль, эмбеддинга лица нет, и личность держится лишь устойчивостью
# трека ByteTrack. Body Re-ID добавляет вторичный сигнал — цветовой дескриптор
# одежды (HSV-гистограммы торса и ног), который одинаков с лица и со спины.
# Используется КОНСЕРВАТИВНО: только чтобы ВОССТАНОВИТЬ личность для трека без
# лица и без уже назначенной личности (новый/переинициализированный трек);
# решение по лицу он никогда не перекрывает.
REID_BODY_ENABLED = True
# Косинусный порог повторного опознания трека по телу. Высокий — чтобы люди в
# разной одежде не сливались (цветовой дескриптор слабее лицевого).
REID_BODY_MATCH_THRESHOLD = 0.82
# Сколько ракурсов тела храним на личность и насколько они должны различаться.
REID_BODY_MAX_EMBEDDINGS = 12
REID_BODY_DIVERSITY_MAX_SIM = 0.97
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
