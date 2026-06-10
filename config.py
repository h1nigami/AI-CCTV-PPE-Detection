from pathlib import Path

BASE_DIR = Path(__file__).parent

MODEL_PATH      = BASE_DIR / "models" / "best.pt"
POSE_MODEL_PATH = BASE_DIR / "models/yolov8n-pose.pt"

CAMERAS = {
    "отдел маркетинга": "rtsp://192.168.0.110:554/user=admin_password=tlJwpbo6_channel=1_stream=0.sdp?real_stream",
    "cam2": "rtsp://192.168.0.108:554/user=admin_password=tlJwpbo6_channel=1_stream=0.sdp?real_stream",
    "отдел продаж": "rtsp://192.168.0.76:554/stream1",
    "холл": "rtsp://192.168.0.103:554/user=admin_password=tlJwpbo6_channel=1_stream=0.sdp?real_stream",

}

CONF_THRESH       = 0.75
MAX_LOG_SIZE      = 100
MIN_CONES         = 2
ZONE_EXPAND_PX    = 20
TOP_RATIO         = 0.4
HAND_CROP_RATIO   = 0.25
DEFECT_DEPTH_MIN  = 15
DEFECT_MIN        = 1
DEFECT_MAX        = 3
MIN_HAND_AREA     = 500
APPROVAL_DURATION = 300
PERSON_ID_GRID    = 50
GESTURE_DISPLAY_DURATION = 3
PRINT_DISPLAY_DURATION   = 3

FONT_PATHS = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
    BASE_DIR / "fonts" / "DejaVuSans.ttf",
]
FONT_SIZE_SMALL  = 14
FONT_SIZE_NORMAL = 18
FONT_SIZE_LARGE  = 22

COLOR_GREEN  = (0, 255, 0)
COLOR_ORANGE = (0, 165, 255)
COLOR_RED    = (0, 0, 255)
COLOR_YELLOW = (0, 255, 255)
COLOR_GOLD   = (0, 215, 255)
COLOR_WHITE  = (255, 255, 255)

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

PRINTER_NAME = "Argox OS-2130D PPLA"