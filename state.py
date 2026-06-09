import time
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from config import APPROVAL_DURATION, PERSON_ID_GRID, MAX_LOG_SIZE

GESTURE_DISPLAY_DURATION = 3
PRINT_DISPLAY_DURATION   = 3


@dataclass
class LogEntry:
    id:        str
    timestamp: str
    message:   str
    category:  str
    cam_id:    str = "cam1"


class DetectionState:
    """Весь изменяемый стейт приложения в одном месте"""

    def __init__(self):
        self._lock            = threading.Lock()
        self.live_active      = False
        self.camera_released  = True
        self._log:      List[LogEntry]         = []
        self._approved: Dict[Tuple, float]     = {}
        self._gesture_until: float             = 0
        self._print_until:   float             = 0

    # ── Лог ──────────────────────────────────

    def add_log(self, entry: LogEntry):
        with self._lock:
            self._log.append(entry)
            if len(self._log) > MAX_LOG_SIZE:
                self._log.pop(0)

    def get_log(self) -> List[LogEntry]:
        with self._lock:
            return list(self._log)

    def clear_log(self):
        with self._lock:
            self._log.clear()

    # ── Пропуска ─────────────────────────────

    def _person_id(self, person_box) -> Tuple:
        cx = int((person_box[0] + person_box[2]) / 2)
        cy = int((person_box[1] + person_box[3]) / 2)
        return (cx // PERSON_ID_GRID, cy // PERSON_ID_GRID)

    def is_approved(self, person_box) -> bool:
        pid = self._person_id(person_box)
        with self._lock:
            expire = self._approved.get(pid)
            if expire is None:
                return False
            if time.time() < expire:
                return True
            del self._approved[pid]
            return False

    def approve(self, person_box):
        pid = self._person_id(person_box)
        with self._lock:
            self._approved[pid] = time.time() + APPROVAL_DURATION
        print(f"Пропуск выдан: ID {pid} на {APPROVAL_DURATION} сек.")

    def clear_approved(self):
        with self._lock:
            self._approved.clear()

    # ── Жест ОК ──────────────────────────────

    def set_gesture_detected(self):
        with self._lock:
            self._gesture_until = time.time() + GESTURE_DISPLAY_DURATION

    def is_gesture_active(self) -> bool:
        with self._lock:
            return time.time() < self._gesture_until

    # ── Печать ───────────────────────────────

    def set_print_triggered(self):
        with self._lock:
            self._print_until = time.time() + PRINT_DISPLAY_DURATION

    def is_print_active(self) -> bool:
        with self._lock:
            return time.time() < self._print_until