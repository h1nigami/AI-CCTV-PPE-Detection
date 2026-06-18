"""Детекция движения (MOG2) перед YOLO — ключевое арх-решение «Motion First».

Типичный кадр со статичной сцены не содержит движения. Вычитание фона MOG2
занимает ~1-2 мс, тогда как YOLO — 20-100 мс. Прогоняя тяжёлую детекцию только
по кадрам с движением, экономим 80-90% CPU/GPU на простаивающих камерах.

`MotionDetector` — на КАЖДУЮ камеру свой экземпляр (фон у камер разный).
Логика консервативна: после спада движения детекция ещё прогоняется
`cooldown_frames` кадров — чтобы не «обрубить» объект, замерший в кадре.
"""
from __future__ import annotations
import cv2
import numpy as np


class MotionResult:
    """Результат одного замера движения."""

    __slots__ = ("motion", "area_ratio", "boxes")

    def __init__(self, motion: bool, area_ratio: float, boxes: list):
        self.motion = motion          # есть ли значимое движение
        self.area_ratio = area_ratio  # доля кадра, покрытая движением [0..1]
        self.boxes = boxes            # bbox'ы областей движения [(x,y,w,h), ...]

    def __bool__(self) -> bool:
        return self.motion


class MotionDetector:
    """Вычитание фона MOG2 + морфология + поиск контуров движения.

    Параметры:
      threshold      — порог бинаризации маски переднего плана (0..255);
      min_area       — минимальная площадь контура (px²), мельче — шум;
      cooldown_frames— сколько кадров после спада движения ещё считать «движением»
                       (антидребезг, удержание детекции);
      history        — длина истории MOG2 (адаптация фона).
    """

    def __init__(self, threshold: int = 30, min_area: int = 1000,
                 cooldown_frames: int = 10, history: int = 200):
        self.threshold = int(threshold)
        self.min_area = int(min_area)
        self.cooldown_frames = int(cooldown_frames)
        self._cooldown = 0
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=history, varThreshold=16, detectShadows=False)
        # Ядро морфологии для подавления одиночных пикселей шума.
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def detect(self, frame: np.ndarray) -> MotionResult:
        """Вернуть MotionResult по кадру. Поддерживает cooldown-удержание."""
        if frame is None or frame.size == 0:
            return MotionResult(False, 0.0, [])
        mask = self._bg.apply(frame)
        # Маска переднего плана → бинаризация → закрытие дыр.
        _, mask = cv2.threshold(mask, self.threshold, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.dilate(mask, self._kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        moved_area = 0
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.min_area:
                continue
            moved_area += area
            boxes.append(cv2.boundingRect(c))

        frame_area = frame.shape[0] * frame.shape[1]
        area_ratio = (moved_area / frame_area) if frame_area else 0.0
        raw_motion = bool(boxes)

        if raw_motion:
            self._cooldown = self.cooldown_frames
            return MotionResult(True, area_ratio, boxes)
        if self._cooldown > 0:
            # Движение спало, но удерживаем детекцию ещё несколько кадров.
            self._cooldown -= 1
            return MotionResult(True, area_ratio, boxes)
        return MotionResult(False, area_ratio, boxes)

    def reset(self):
        self._cooldown = 0
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=16, detectShadows=False)
