import time
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from config import APPROVAL_DURATION, PERSON_ID_GRID, MAX_LOG_SIZE


@dataclass
class LogEntry:
    id:        str
    timestamp: str
    message:   str
    category:  str  # "норма" | "внимание" | "нарушение"


class DetectionState:
    """Весь изменяемый стейт приложения в одном месте"""

    def __init__(self):
        self._lock            = threading.Lock()
        self.live_active      = False
        self.camera_released  = True
        self._log: List[LogEntry]        = []
        self._approved: Dict[Tuple, float] = {}

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