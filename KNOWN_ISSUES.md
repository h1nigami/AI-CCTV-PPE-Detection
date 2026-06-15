# Known Issues

## onnxruntime-gpu на Jetson ARM64

**Проблема:** На Jetson Orin (aarch64, JetPack 6.x, CUDA 12.6) нет готового wheel
`onnxruntime-gpu` ни в PyPI, ни в NVIDIA NGC, ни в Azure DevOps фиде (там только `win_amd64`).

**Сейчас:** InsightFace работает на CPU через `onnxruntime` 1.23.2. YOLO на GPU (CUDA через PyTorch).

**Варианты решения:**
1. Собрать из исходников (~1-3ч):
   ```bash
   git clone https://github.com/microsoft/onnxruntime
   cd onnxruntime
   ./build.sh --config Release --build_shared_lib --parallel --use_cuda \
     --cuda_home /usr/local/cuda --cudnn_home /usr/lib/aarch64-linux-gnu
   ```
2. Найти pre-built wheel в сообществе (Jetson Zoo, NVIDIA DevZone)
3. Оставить на CPU (на Orin ~50-100ms на детекцию лиц — приемлемо)

**Статус:** Отложено.
