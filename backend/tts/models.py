"""Скачивание/кэширование голосовых моделей Piper из HuggingFace.

Идемпотентно (как download_models.py для InsightFace): если .onnx и .onnx.json
уже на месте — ничего не качает. В Docker качается в рантайме (models/ —
volume), не на этапе build. При любой ошибке возвращает None → сервис мягко
деградирует (фронт откатывается на Web Speech).
"""
from pathlib import Path
from typing import Optional, Tuple

# Репозиторий голосов Piper.
_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _voice_url_dir(model_name: str) -> str:
    """ru_RU-irina-medium → ru/ru_RU/irina/medium (путь внутри репозитория)."""
    parts = model_name.split("-")
    if len(parts) < 3:
        raise ValueError(f"Не разобрать имя голоса Piper: {model_name}")
    lang_full, speaker, quality = parts[0], parts[1], parts[2]
    lang = lang_full.split("_")[0]
    return f"{lang}/{lang_full}/{speaker}/{quality}"


def _is_present(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def ensure_model(model_dir, model_name: str) -> Optional[Tuple[Path, Path]]:
    """Гарантировать наличие .onnx и .onnx.json модели; вернуть пути или None."""
    model_dir = Path(model_dir)
    onnx_path = model_dir / f"{model_name}.onnx"
    config_path = model_dir / f"{model_name}.onnx.json"
    if _is_present(onnx_path) and _is_present(config_path):
        return onnx_path, config_path
    try:
        import requests
        model_dir.mkdir(parents=True, exist_ok=True)
        url_dir = _voice_url_dir(model_name)
        for path, fname in ((onnx_path, f"{model_name}.onnx"),
                            (config_path, f"{model_name}.onnx.json")):
            if _is_present(path):
                continue
            url = f"{_HF_BASE}/{url_dir}/{fname}?download=true"
            print(f"[tts] Скачивание {fname} ...")
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                tmp = path.with_suffix(path.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
                tmp.replace(path)
        return onnx_path, config_path
    except Exception as e:
        print(f"[tts] Не удалось скачать модель {model_name}: {e}")
        return None
