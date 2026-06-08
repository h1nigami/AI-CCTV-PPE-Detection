# ─── Модели ───────────────────────────────────
MODEL_PATH       = "models/best.pt"
POSE_MODEL_PATH  = "models/yolov8n-pose.pt"

# ─── Камера ───────────────────────────────────
CAMERA_SOURCE    = "rtsp://192.168.0.124:554/stream1"

# ─── Детекция ─────────────────────────────────
CONF_THRESH      = 0.75
MAX_LOG_SIZE     = 20

# ─── Опасная зона ─────────────────────────────
MIN_CONES        = 2
ZONE_EXPAND_PX   = 20

# ─── Жест ОК ──────────────────────────────────
HAND_CROP_RATIO  = 0.25
DEFECT_DEPTH_MIN = 15
DEFECT_MIN       = 1
DEFECT_MAX       = 3
MIN_HAND_AREA    = 500
TOP_RATIO        = 0.4

# ─── Пропуск ──────────────────────────────────
APPROVAL_DURATION = 300   # секунд
PERSON_ID_GRID    = 50    # пикселей

# ─── Шрифты ───────────────────────────────────
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
FONT_SIZE_SMALL  = 14
FONT_SIZE_NORMAL = 18
FONT_SIZE_LARGE  = 22

# ─── Цвета BGR ────────────────────────────────
COLOR_GREEN  = (0, 255, 0)
COLOR_ORANGE = (0, 165, 255)
COLOR_RED    = (0, 0, 255)
COLOR_YELLOW = (0, 255, 255)
COLOR_GOLD   = (0, 215, 255)
COLOR_WHITE  = (255, 255, 255)

# ─── Названия классов ─────────────────────────
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
    9: "Транспорт"
}