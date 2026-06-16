from dataclasses import dataclass


@dataclass
class LogEntry:
    id: str
    timestamp: str
    message: str
    category: str
    cam_id: str = "cam1"
    global_id: int = 0
