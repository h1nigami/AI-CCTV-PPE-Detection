#!/usr/bin/env python3
"""
Конвертация YOLO-моделей .pt → TorchScript (.torchscript) для ARM64-серверов
с тензорными ядрами (Jetson Orin, Grace Hopper и др.).

Использование:
    python convert_to_torchscript.py [--models best pose] [--imgsz 640] [--half]

Параметры:
    --models   список моделей для конвертации: best, pose, nano (по умолчанию: best pose)
    --imgsz    размер входного изображения (по умолчанию: 640)
    --half     экспортировать в FP16 (требует CUDA или устройство с тензорными ядрами)
    --device   устройство: 'cpu', '0', 'cuda:0' и т.д. (авто по умолчанию)
    --verify   проверить инференс на тестовом изображении после конвертации

Результат: рядом с .pt-файлом создаётся <name>.torchscript
Приоритет загрузки в runtime: .engine > .torchscript > .pt
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

BASE_DIR = Path(__file__).parent

MODELS = {
    "best": BASE_DIR / "models" / "best.pt",
    "pose": BASE_DIR / "models" / "yolov8n-pose.pt",
    "nano": BASE_DIR / "models" / "yolov8n.pt",
}


def convert_model(name: str, pt_path: Path, imgsz: int, half: bool, device: str, verify: bool) -> Path:
    ts_path = pt_path.with_suffix(".torchscript")

    if not pt_path.exists():
        print(f"  [ПРОПУСК] {pt_path} не найден")
        return None

    print(f"\n{'='*60}")
    print(f"  Модель : {name} ({pt_path.name})")
    print(f"  Размер : {imgsz}x{imgsz}")
    print(f"  FP16   : {'да' if half else 'нет'}")
    print(f"  Устройство: {device}")
    print(f"{'='*60}")

    model = YOLO(str(pt_path))

    t0 = time.time()
    exported = model.export(
        format="torchscript",
        imgsz=imgsz,
        half=half,
        device=device,
        optimize=True,   # torch.utils.mobile_optimizer — полезно для ARM
        simplify=False,  # ONNX-simplifier не нужен для TorchScript
    )
    elapsed = time.time() - t0

    # Ultralytics возвращает путь к файлу или сохраняет рядом
    out = Path(exported) if exported else ts_path
    if not out.exists():
        # Ultralytics иногда кладёт рядом с .pt
        candidate = pt_path.parent / (pt_path.stem + ".torchscript")
        if candidate.exists():
            out = candidate

    print(f"  Сохранено: {out}  ({elapsed:.1f}с)")

    if verify and out.exists():
        _verify(name, out, imgsz, device)

    return out


def _verify(name: str, ts_path: Path, imgsz: int, device: str):
    """Быстрая проверка — один инференс на нулевом изображении."""
    print(f"  Проверка инференса...")
    try:
        model = YOLO(str(ts_path))
        dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
        t0 = time.time()
        res = model(dummy, verbose=False)
        ms = (time.time() - t0) * 1000
        print(f"  OK — {ms:.0f} мс, боксов: {len(res[0].boxes)}")
    except Exception as e:
        print(f"  ОШИБКА проверки: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Конвертация YOLO .pt → TorchScript для ARM64"
    )
    parser.add_argument(
        "--models", nargs="+", default=["best", "pose"],
        choices=list(MODELS.keys()),
        help="Модели для конвертации (по умолчанию: best pose)",
    )
    parser.add_argument("--imgsz", type=int, default=640, help="Размер входа (по умолч. 640)")
    parser.add_argument("--half", action="store_true", help="FP16 (требует CUDA/тензорные ядра)")
    parser.add_argument(
        "--device", default=None,
        help="Устройство: cpu, 0, cuda:0 (авто если не задано)",
    )
    parser.add_argument("--verify", action="store_true", help="Проверить инференс после экспорта")
    args = parser.parse_args()

    if args.device is None:
        args.device = "0" if torch.cuda.is_available() else "cpu"

    if args.half and args.device == "cpu":
        print("ПРЕДУПРЕЖДЕНИЕ: FP16 на CPU не поддерживается, отключаю --half")
        args.half = False

    print(f"PyTorch {torch.__version__}")
    print(f"CUDA доступна: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    results = {}
    for model_name in args.models:
        pt_path = MODELS[model_name]
        out = convert_model(
            name=model_name,
            pt_path=pt_path,
            imgsz=args.imgsz,
            half=args.half,
            device=args.device,
            verify=args.verify,
        )
        results[model_name] = out

    print(f"\n{'='*60}")
    print("Итог:")
    for name, path in results.items():
        status = f"OK → {path}" if path and path.exists() else "НЕ КОНВЕРТИРОВАН"
        print(f"  {name:8s}: {status}")
    print(f"\nПосле конвертации runtime автоматически подхватит .torchscript")
    print("(приоритет: .engine > .torchscript > .pt)")


if __name__ == "__main__":
    main()
