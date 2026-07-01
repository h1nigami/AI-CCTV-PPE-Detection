"""Скачивание/кэширование глубокой Body-Re-ID модели (OSNet ONNX) из HuggingFace.

Идемпотентно (как download_models.py для InsightFace и tts/models.py для Piper):
если .onnx уже на месте — ничего не качает. Модель маленькая (~0.9 МБ,
osnet_x0_25), поэтому докачка дешёвая. В Docker качается в рантайме (models/ —
volume), не на этапе build. При любой ошибке возвращает None → BodyRecognizer
мягко деградирует на цветовой дескриптор.
"""
import os
from pathlib import Path
from typing import Optional


def _is_present(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def ensure_body_model(model_dir, model_name: str, url: str) -> Optional[Path]:
    """Гарантировать наличие <model_dir>/<model_name>.onnx; вернуть путь или None.

    REID_BODY_OFFLINE=1 запрещает скачивание (тесты/офлайн-окружение): если модели
    нет локально — возвращает None, и body Re-ID деградирует на цветовой дескриптор."""
    model_dir = Path(model_dir)
    onnx_path = model_dir / f"{model_name}.onnx"
    if _is_present(onnx_path):
        return onnx_path
    if os.environ.get("REID_BODY_OFFLINE") == "1":
        return None
    # Офлайн — не виснем на скачивании, сразу деградируем на цветовой дескриптор.
    from backend.netutil import is_online
    if not is_online():
        print("[ReID/body] Сети нет — пропуск скачивания OSNet, цветовой fallback")
        return None
    try:
        import requests
        model_dir.mkdir(parents=True, exist_ok=True)
        print(f"[ReID/body] Скачивание {model_name}.onnx ...")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            tmp = onnx_path.with_suffix(onnx_path.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
            tmp.replace(onnx_path)
        print(f"[ReID/body] Модель готова: {onnx_path}")
        return onnx_path
    except Exception as e:
        print(f"[ReID/body] Не удалось скачать модель {model_name}: {e}")
        return None
