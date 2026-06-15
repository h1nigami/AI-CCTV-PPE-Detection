"""Экспорт YOLO-моделей в TensorRT engine (FP16) при первом запуске."""
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

def export_if_needed():
    models = [
        ("best.pt", "best.engine"),
        ("yolov8n-pose.pt", "yolov8n-pose.engine"),
    ]
    for pt_name, engine_name in models:
        pt_path = MODELS_DIR / pt_name
        engine_path = MODELS_DIR / engine_name
        if engine_path.exists():
            print(f"[Engine] {engine_name} уже существует")
            continue
        if not pt_path.exists():
            print(f"[Engine] {pt_name} не найден, пропускаю")
            continue
        print(f"[Engine] Экспорт {pt_name} → {engine_name} (FP16)...")
        sys.stdout.flush()
        from ultralytics import YOLO
        model = YOLO(str(pt_path))
        model.export(
            format="engine",
            half=True,
            device=0,
            imgsz=640,
            verbose=False,
        )
        print(f"[Engine] {engine_name} готов")
        sys.stdout.flush()


if __name__ == "__main__":
    export_if_needed()
