import cv2
import numpy as np
from pathlib import Path
from typing import Optional

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False


class FaceDetector:
    def __init__(self, model_path: str = "models/yolov8n-face.pt",
                 conf: float = 0.5):
        self.model_path = model_path
        self.conf = conf
        self._model = None
        if ULTRALYTICS_AVAILABLE and Path(model_path).exists():
            try:
                self._model = YOLO(model_path)
                print(f"[FaceDetector] Модель загружена: {model_path}")
            except Exception as e:
                print(f"[FaceDetector] Ошибка: {e}")

    def detect(self, frame: np.ndarray) -> list[tuple]:
        faces = []
        if self._model is None:
            return faces
        try:
            results = self._model(frame, conf=self.conf, verbose=False)
            for r in results:
                if r.boxes is not None:
                    for box in r.boxes.xyxy.cpu().numpy():
                        x1, y1, x2, y2 = map(int, box[:4])
                        x1, y1 = max(0, x1), max(0, y1)
                        faces.append((x1, y1, x2, y2))
        except Exception as e:
            print(f"[FaceDetector] Ошибка детекции: {e}")
        return faces

    def crop_face(self, frame: np.ndarray, face_box: tuple,
                  margin: float = 0.3) -> Optional[np.ndarray]:
        x1, y1, x2, y2 = face_box
        h, w = frame.shape[:2]
        mw = int((x2 - x1) * margin)
        mh = int((y2 - y1) * margin)
        x1 = max(0, x1 - mw)
        y1 = max(0, y1 - mh)
        x2 = min(w, x2 + mw)
        y2 = min(h, y2 + mh)
        return frame[y1:y2, x1:x2]
