from __future__ import annotations
import json
from pathlib import Path

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
MIN_CONES = 2
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
REID_MAX_EMBEDDINGS = 5
REID_MAX_AGE_DAYS = 30
REID_GALLERY_PATH = BASE_DIR / "data" / "face_gallery.pkl"
REID_DET_SIZE = (640, 640)
REID_FRAME_SKIP = 3
# Анти-замусоривание галереи: с одного трека добавляем эмбеддинг не чаще
# REID_STORE_INTERVAL сек и только при качестве >= REID_MIN_STORE_QUALITY,
# иначе один и тот же кадр (кэш детектора лиц) вытесняет эталонные эмбеддинги.
REID_MIN_STORE_QUALITY = 0.55
REID_STORE_INTERVAL = 1.5
# Насколько ниже порога регистрации «прилипает» текущая личность трека
# (один плохой кадр не сбрасывает имя на нового «Гостя»). Порог липкости
# = threshold_for(quality) - margin, но не ниже 0.35: разные люди (~0.2) не
# прилипают, один человек в другом ракурсе (~0.4-0.7) — удерживается.
REID_STICKY_MARGIN = 0.10

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
