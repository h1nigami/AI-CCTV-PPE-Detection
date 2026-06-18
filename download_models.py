"""Докачка ML-моделей, которых нет в git, после клонирования репозитория.

В git лежат только YOLO-веса (`models/*.pt`). Модель распознавания лиц
`models/buffalo_l/` в `.gitignore` (бинарники ~280 МБ), поэтому после `git clone`
её нужно получить отдельно. Этот скрипт делает это идемпотентно: если модель уже
на месте — ничего не качает.

ВАЖНО: качать нужно в РАНТАЙМЕ (а не на этапе docker build), потому что
docker-compose монтирует `./models` как volume с хоста и перекрывает то, что
COPY положил в образ. Поэтому скрипт вызывается из entrypoint.sh (после монтирования)
и/или вручную после клона: `python3 download_models.py`.

Каталог назначения берётся из INSIGHTFACE_ROOT (в контейнере = /app), иначе —
каталог репозитория; модель кладётся в <root>/models/buffalo_l.
"""
import os
import sys
from pathlib import Path

MODEL = "buffalo_l"
REQUIRED = ["det_10g.onnx", "w600k_r50.onnx"]


def main() -> int:
    root = os.environ.get("INSIGHTFACE_ROOT") or str(Path(__file__).resolve().parent)
    target = Path(root) / "models" / MODEL

    if target.is_dir() and all((target / f).exists() for f in REQUIRED):
        print(f"[Models] {MODEL} уже на месте: {target}")
        return 0

    print(f"[Models] {MODEL} отсутствует — скачиваю в {target} ...")
    try:
        # FaceAnalysis при отсутствии модели сам скачивает и распаковывает её
        # в <root>/models/<name>. CPU-провайдера достаточно для докачки.
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name=MODEL, root=root, providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1)
        print(f"[Models] {MODEL} готова: {target}")
        return 0
    except Exception as e:
        print(f"[Models] Не удалось скачать {MODEL}: {e}", file=sys.stderr)
        print(
            "Скачайте вручную и распакуйте в "
            f"{target}/:\n"
            "  https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
