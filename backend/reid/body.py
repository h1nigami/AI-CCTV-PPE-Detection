"""Body Re-ID — дескриптор внешнего вида человека для опознания «со спины».

Лицевой Re-ID (InsightFace) требует фронтального лица. Когда человек повёрнут
спиной/боком, лица нет и личность держится только устойчивостью трека ByteTrack.
Этот модуль извлекает дескриптор внешнего вида (одежда+силуэт), одинаковый с лица
и со спины, и используется как вторичный сигнал для восстановления личности трека
без лица.

Два бэкенда (выбирается автоматически в __init__):
  • DEEP (основной) — глубокая Re-ID сеть OSNet (ONNX, onnxruntime). Семантический
    512-мерный дескриптор личности, устойчивый к ракурсу. Требует скачанной модели
    (см. body_models.ensure_body_model) и onnxruntime (он и так стоит для InsightFace).
  • COLOR (fallback) — цветовой дескриптор (HSV-гистограммы торса/ног), без внешних
    зависимостей. Включается, если deep-модель/onnxruntime недоступны — система
    продолжает работать (мягкая деградация, как Piper TTS → Web Speech).

Оба дескриптора L2-нормированы → сравнение обычным косинусом (см. FaceGallery).
Дескрипторы разной размерности (deep 512 vs color 2·h_bins·s_bins) не смешиваются:
галерея сравнивает только эмбеддинги одинаковой длины.

Свойства `backend`, `match_threshold`, `diversity_max_sim` сообщают вызывающему
(main.py → state.configure_body), какие пороги применять к активному дескриптору.
"""
from __future__ import annotations
from typing import List, Optional, Sequence
import numpy as np
import cv2

from backend.config import (
    REID_BODY_MIN_AREA, REID_BODY_MODEL, REID_BODY_MODEL_DIR, REID_BODY_MODEL_URL,
    REID_BODY_INPUT_W, REID_BODY_INPUT_H, REID_BODY_ONNX_BATCH,
    REID_BODY_MATCH_THRESHOLD, REID_BODY_DIVERSITY_MAX_SIM,
    REID_BODY_MATCH_THRESHOLD_COLOR, REID_BODY_DIVERSITY_MAX_SIM_COLOR,
)

# ImageNet-нормализация (стандарт torchreid/OSNet), порядок каналов RGB.
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class BodyRecognizer:
    def __init__(self, h_bins: int = 16, s_bins: int = 8,
                 min_area: int = REID_BODY_MIN_AREA, use_deep: bool = True):
        self.h_bins = h_bins
        self.s_bins = s_bins
        self.min_area = min_area
        # Длина цветового дескриптора: две зоны (торс + ноги) × (h_bins × s_bins).
        self.color_dim = 2 * h_bins * s_bins

        # ── Попытка поднять глубокий бэкенд (OSNet ONNX) ──────────────────────
        self._session = None
        self._input_name: Optional[str] = None
        self._in_w = REID_BODY_INPUT_W
        self._in_h = REID_BODY_INPUT_H
        self._onnx_batch = REID_BODY_ONNX_BATCH
        if use_deep:
            self._try_load_deep()

    def _try_load_deep(self):
        """Загрузить OSNet ONNX в onnxruntime. При любой ошибке остаётся None →
        extract() работает на цветовом fallback."""
        try:
            from backend.reid.body_models import ensure_body_model
            model_path = ensure_body_model(REID_BODY_MODEL_DIR, REID_BODY_MODEL,
                                           REID_BODY_MODEL_URL)
            if model_path is None:
                return
            import onnxruntime as ort
            providers = ort.get_available_providers()
            # CUDA если есть, иначе CPU (как у FaceRecognizer).
            use = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
                   if p in providers] or ["CPUExecutionProvider"]
            sess = ort.InferenceSession(str(model_path), providers=use)
            inp = sess.get_inputs()[0]
            self._input_name = inp.name
            # Форма входа [N, 3, H, W]; берём фиксированный батч если он статический.
            shape = inp.shape
            if isinstance(shape[0], int) and shape[0] > 0:
                self._onnx_batch = shape[0]
            if isinstance(shape[2], int):
                self._in_h = shape[2]
            if isinstance(shape[3], int):
                self._in_w = shape[3]
            self._session = sess
            print(f"[ReID/body] OSNet активен ({REID_BODY_MODEL}, "
                  f"вход {self._in_w}x{self._in_h}, батч {self._onnx_batch}, {use[0]})")
        except Exception as e:
            self._session = None
            print(f"[ReID/body] Глубокий бэкенд недоступен ({e}); цветовой fallback")

    # ── Свойства активного бэкенда (для подбора порогов в state) ─────────────
    @property
    def backend(self) -> str:
        return "deep" if self._session is not None else "color"

    @property
    def match_threshold(self) -> float:
        return (REID_BODY_MATCH_THRESHOLD if self._session is not None
                else REID_BODY_MATCH_THRESHOLD_COLOR)

    @property
    def diversity_max_sim(self) -> float:
        return (REID_BODY_DIVERSITY_MAX_SIM if self._session is not None
                else REID_BODY_DIVERSITY_MAX_SIM_COLOR)

    # ── Подготовка bbox ──────────────────────────────────────────────────────
    def _clamp_box(self, frame: np.ndarray, person_box) -> Optional[tuple]:
        """Обрезать bbox по кадру и отсеять слишком мелкие/пустые. Вернуть
        (x1,y1,x2,y2) или None."""
        if frame is None or person_box is None:
            return None
        h_img, w_img = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in person_box[:4]]
        x1 = max(0, min(x1, w_img - 1))
        x2 = max(0, min(x2, w_img))
        y1 = max(0, min(y1, h_img - 1))
        y2 = max(0, min(y2, h_img))
        if x2 - x1 < 8 or y2 - y1 < 16:
            return None
        if (x2 - x1) * (y2 - y1) < self.min_area:
            return None
        return x1, y1, x2, y2

    # ── Публичный API ────────────────────────────────────────────────────────
    def extract(self, frame: np.ndarray, person_box) -> Optional[np.ndarray]:
        """Вернуть L2-нормированный дескриптор внешнего вида человека или None,
        если bbox слишком мал/пуст. ВАЖНО: подавать ЧИСТЫЙ кадр (без нарисованных
        рамок/заливки опасной зоны), иначе оверлеи исказят дескриптор."""
        return self.extract_batch(frame, [person_box])[0]

    def extract_batch(self, frame: np.ndarray,
                      person_boxes: Sequence) -> List[Optional[np.ndarray]]:
        """Дескрипторы для списка людей одним проходом. Для deep-бэкенда это один
        инференс на кадр (кропы гоняются пачками по onnx_batch) вместо одного на
        человека. Возвращает список той же длины, None для негодных bbox."""
        if not person_boxes:
            return []
        if self._session is not None:
            return self._extract_deep_batch(frame, person_boxes)
        return [self._extract_color(frame, b) for b in person_boxes]

    # ── DEEP (OSNet) ─────────────────────────────────────────────────────────
    def _preprocess(self, frame: np.ndarray, box: tuple) -> np.ndarray:
        """Кроп человека → вход OSNet (3, H, W), RGB, ImageNet-нормализация."""
        x1, y1, x2, y2 = box
        crop = frame[y1:y2, x1:x2]
        crop = cv2.resize(crop, (self._in_w, self._in_h), interpolation=cv2.INTER_LINEAR)
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        crop = (crop - _IMAGENET_MEAN) / _IMAGENET_STD
        return np.transpose(crop, (2, 0, 1))  # HWC → CHW

    def _extract_deep_batch(self, frame: np.ndarray,
                            person_boxes: Sequence) -> List[Optional[np.ndarray]]:
        results: List[Optional[np.ndarray]] = [None] * len(person_boxes)
        # Готовим кропы только для годных bbox, запоминая их позиции.
        tensors: List[np.ndarray] = []
        positions: List[int] = []
        for i, pbox in enumerate(person_boxes):
            box = self._clamp_box(frame, pbox)
            if box is None:
                continue
            try:
                tensors.append(self._preprocess(frame, box))
                positions.append(i)
            except Exception:
                continue
        if not tensors:
            return results
        batch = self._onnx_batch
        for start in range(0, len(tensors), batch):
            chunk = tensors[start:start + batch]
            n = len(chunk)
            arr = np.stack(chunk).astype(np.float32)
            if batch and n < batch:
                # Паддинг до фиксированного батча модели (лишние выходы отбросим).
                pad = np.zeros((batch - n, *arr.shape[1:]), dtype=np.float32)
                arr = np.concatenate([arr, pad], axis=0)
            try:
                out = self._session.run(None, {self._input_name: arr})[0]
            except Exception as e:
                print(f"[ReID/body] Ошибка инференса OSNet: {e}")
                continue
            for j in range(n):
                vec = np.asarray(out[j], dtype=np.float32).flatten()
                norm = float(np.linalg.norm(vec))
                if norm < 1e-6:
                    continue
                results[positions[start + j]] = vec / norm
        return results

    # ── COLOR (fallback) ─────────────────────────────────────────────────────
    def _region_hist(self, region: np.ndarray) -> np.ndarray:
        """L1-нормированная совместная HSV-гистограмма (каналы H и S) региона."""
        size = self.h_bins * self.s_bins
        if region is None or region.size == 0:
            return np.zeros(size, dtype=np.float32)
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None,
                            [self.h_bins, self.s_bins], [0, 180, 0, 256])
        hist = hist.flatten().astype(np.float32)
        total = float(hist.sum())
        if total > 0:
            hist /= total
        return hist

    def _extract_color(self, frame: np.ndarray, person_box) -> Optional[np.ndarray]:
        box = self._clamp_box(frame, person_box)
        if box is None:
            return None
        x1, y1, x2, y2 = box
        crop = frame[y1:y2, x1:x2]
        ch, cw = crop.shape[:2]
        # Берём центральную вертикаль (отрезаем фон по бокам bbox).
        cx1, cx2 = int(cw * 0.2), int(cw * 0.8)
        if cx2 - cx1 < 4:
            cx1, cx2 = 0, cw
        # Торс (пропускаем голову) и ноги — две зоны одежды.
        torso = crop[int(ch * 0.15):int(ch * 0.55), cx1:cx2]
        legs = crop[int(ch * 0.55):int(ch * 0.95), cx1:cx2]
        vec = np.concatenate([self._region_hist(torso),
                              self._region_hist(legs)]).astype(np.float32)
        norm = float(np.linalg.norm(vec))
        if norm < 1e-6:
            return None
        return vec / norm
