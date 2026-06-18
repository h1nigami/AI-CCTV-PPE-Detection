"""Body Re-ID — дескриптор внешнего вида человека для опознания «со спины».

Лицевой Re-ID (InsightFace) требует фронтального лица. Когда человек повёрнут
спиной/боком, лица нет и личность держится только устойчивостью трека ByteTrack.
Этот модуль извлекает цветовой дескриптор одежды (HSV-гистограммы по торсу и
ногам), который одинаков с лица и со спины, и используется как вторичный сигнал
для восстановления личности трека без лица.

Дескриптор L2-нормирован → косинусная близость двух дескрипторов лежит в [0, 1]
(гистограммы неотрицательны). Сравнение — обычный косинус (см. FaceGallery).

`BodyRecognizer.extract()` намеренно изолирован: при желании цветовой бэкенд
можно заменить на глубокую Re-ID модель (OSNet/torchreid), сохранив интерфейс
(вернуть L2-нормированный вектор фиксированной длины или None).
"""
from __future__ import annotations
from typing import Optional
import numpy as np
import cv2

from backend.config import REID_BODY_MIN_AREA


class BodyRecognizer:
    def __init__(self, h_bins: int = 16, s_bins: int = 8,
                 min_area: int = REID_BODY_MIN_AREA):
        self.h_bins = h_bins
        self.s_bins = s_bins
        self.min_area = min_area
        # Длина дескриптора: две зоны (торс + ноги) × (h_bins × s_bins).
        self.dim = 2 * h_bins * s_bins

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

    def extract(self, frame: np.ndarray, person_box) -> Optional[np.ndarray]:
        """Вернуть L2-нормированный дескриптор внешнего вида человека или None,
        если bbox слишком мал/пуст (дескриптор был бы ненадёжен).

        ВАЖНО: подавать ЧИСТЫЙ кадр (без нарисованных рамок/заливки опасной зоны),
        иначе оверлеи исказят цвета одежды."""
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
