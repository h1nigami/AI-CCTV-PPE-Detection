"""Отслеживание перемещений людей: кто сидит на месте, кто встал и куда пошёл.

Модуль работает на уже готовых детекциях людей (`process_frame`) и их устойчивых
идентификаторах (`track_id`/`global_id`) — новую ML-модель не подключаем. Вся
логика — чистая геометрия по «точке ног» (низ-центр bbox), поэтому тестируется без
кадров/GPU (как `MotionDetector`/`DetectionState`).

Конечный автомат на человека (масштаб порогов = рост bbox → не зависит от
разрешения и дистанции):
- ``sitting`` — точка ног держится у «якоря места» (anchor) в пределах допуска;
  копится непрерывное время `seated_seconds` (сколько человек сидит на месте).
- ``moving`` — сместился от якоря дальше порога «встал» → фиксируется событие
  «встал с места», рисуется траектория ухода. Замер в новой точке дольше
  `settle_sec` → там ставится новый якорь (человек сел на новое место).

Пороги читаются ЖИВЫМИ из рантайм-настроек (`get_detection_setting`) — правка из
UI применяется без рестарта. Явные значения в конструкторе (тесты) их
переопределяют.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from backend.config import get_detection_setting

# Дефолты порогов (fallback, если рантайм-настройки нет) — совпадают со спекой в
# config.py. Доли масштабируются ростом человека (высота bbox).
_DEF_STILL_FRAC = 0.15   # допуск «на месте» (доля роста)
_DEF_MOVE_FRAC = 0.6     # смещение от якоря, считающееся «встал» (доля роста)
_DEF_SETTLE_SEC = 2.0    # сколько держаться на месте, чтобы зафиксировать якорь
_DEF_TRAIL_SEC = 15.0    # длина следа траектории по времени

# Человек, не обновлявшийся дольше этого, удаляется из трекера.
PERSON_EXPIRY_SEC = 60.0
# Масштаб (рост bbox) зажимаем снизу: у мелких/далёких людей пороги не должны
# схлопываться в пиксельный шум детекции.
_MIN_SCALE_PX = 40.0
# Страховочный лимит числа точек следа (помимо обрезки по времени).
_MAX_TRAIL_POINTS = 512
# Мягкое подтягивание якоря к текущей точке при микродрейфе (катящийся стул).
_ANCHOR_EMA = 0.05


@dataclass
class _PersonTrack:
    name: str = ""
    # (t, x, y) — точка ног во времени.
    positions: Deque[Tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=_MAX_TRAIL_POINTS))
    scale: float = _MIN_SCALE_PX
    anchor: Optional[Tuple[float, float]] = None
    state: str = "moving"                 # "sitting" | "moving"
    sitting_since: Optional[float] = None
    stood_up_at: Optional[float] = None
    last_update: float = 0.0


@dataclass
class MovementInfo:
    """Результат по одному человеку за кадр (в порядке входного списка)."""
    key: str
    name: str
    state: str                            # "sitting" | "moving"
    seated_seconds: float                 # непрерывное время на месте
    anchor: Optional[Tuple[float, float]]
    trail: List[Tuple[float, float]]      # точки следа (x, y) для отрисовки
    just_stood_up: bool                   # в этом кадре встал с места
    just_sat_down: bool                   # в этом кадре сел (зафиксирован якорь)


class MovementTracker:
    """По экземпляру на камеру. `update` вызывается на каждом кадре со всеми
    видимыми людьми; возвращает `MovementInfo` в том же порядке."""

    def __init__(self, still_frac: Optional[float] = None,
                 move_frac: Optional[float] = None,
                 settle_sec: Optional[float] = None,
                 trail_sec: Optional[float] = None,
                 expiry_sec: float = PERSON_EXPIRY_SEC):
        # None → читать живьём из рантайм-настроек (hot-reload). Явное значение
        # (тесты) переопределяет.
        self._still_frac = still_frac
        self._move_frac = move_frac
        self._settle_sec = settle_sec
        self._trail_sec = trail_sec
        self._expiry_sec = expiry_sec
        self._tracks: Dict[str, _PersonTrack] = {}

    @staticmethod
    def _setting(override: Optional[float], key: str, default: float) -> float:
        if override is not None:
            return override
        val = get_detection_setting(key)
        return default if val is None else float(val)

    def update(self, persons: List[dict], now: Optional[float] = None) -> List[MovementInfo]:
        """persons: список словарей {'key': str, 'box': (x1,y1,x2,y2), 'name': str}."""
        if now is None:
            now = time.time()
        still_frac = self._setting(self._still_frac, "movement_still_frac", _DEF_STILL_FRAC)
        move_frac = self._setting(self._move_frac, "movement_move_frac", _DEF_MOVE_FRAC)
        settle_sec = self._setting(self._settle_sec, "movement_settle_sec", _DEF_SETTLE_SEC)
        trail_sec = self._setting(self._trail_sec, "movement_trail_sec", _DEF_TRAIL_SEC)

        results = [self._update_one(p, now, still_frac, move_frac, settle_sec, trail_sec)
                   for p in persons]
        self.cleanup(now)
        return results

    def _update_one(self, p: dict, now: float, still_frac: float, move_frac: float,
                    settle_sec: float, trail_sec: float) -> MovementInfo:
        key = p["key"]
        x1, y1, x2, y2 = p["box"]
        name = p.get("name", "") or ""
        foot_x = (float(x1) + float(x2)) / 2.0   # точка ног: низ-центр bbox
        foot_y = float(y2)
        height = max(_MIN_SCALE_PX, float(y2) - float(y1))

        tr = self._tracks.get(key)
        if tr is None:
            tr = _PersonTrack()
            self._tracks[key] = tr
        if name:
            tr.name = name
        tr.scale = height
        tr.last_update = now
        tr.positions.append((now, foot_x, foot_y))
        self._prune_trail(tr, now, trail_sec)

        still_thr = still_frac * height
        move_thr = move_frac * height
        just_stood_up = False
        just_sat_down = False

        if tr.anchor is None:
            # Место ещё не зафиксировано: ждём, пока человек постоит/посидит смирно.
            if self._settled(tr, now, settle_sec, still_thr):
                tr.anchor = self._recent_centroid(tr, now, settle_sec)
                tr.state = "sitting"
                tr.sitting_since = self._recent_start(tr, now, settle_sec)
                just_sat_down = True
        else:
            dist = math.hypot(foot_x - tr.anchor[0], foot_y - tr.anchor[1])
            if tr.state == "sitting":
                if dist > move_thr:
                    # Встал с места и пошёл.
                    tr.state = "moving"
                    tr.stood_up_at = now
                    tr.sitting_since = None
                    just_stood_up = True
                elif dist <= still_thr:
                    # Микродрейф (катящийся стул) — мягко подтягиваем якорь.
                    ax, ay = tr.anchor
                    tr.anchor = (ax + (foot_x - ax) * _ANCHOR_EMA,
                                 ay + (foot_y - ay) * _ANCHOR_EMA)
            else:  # moving — не сел ли на новом месте
                if self._settled(tr, now, settle_sec, still_thr):
                    tr.anchor = self._recent_centroid(tr, now, settle_sec)
                    tr.state = "sitting"
                    tr.sitting_since = self._recent_start(tr, now, settle_sec)
                    just_sat_down = True

        seated = ((now - tr.sitting_since)
                  if (tr.state == "sitting" and tr.sitting_since is not None) else 0.0)
        trail = [(x, y) for (_, x, y) in tr.positions]
        return MovementInfo(
            key=key, name=tr.name, state=tr.state,
            seated_seconds=max(0.0, seated), anchor=tr.anchor, trail=trail,
            just_stood_up=just_stood_up, just_sat_down=just_sat_down)

    # ── Вспомогательные (чистые) ──────────────────────────────────────────────
    @staticmethod
    def _prune_trail(tr: _PersonTrack, now: float, trail_sec: float):
        # Обрезаем след по времени, оставляя минимум 2 точки для линии.
        while len(tr.positions) > 2 and (now - tr.positions[0][0]) > trail_sec:
            tr.positions.popleft()

    @staticmethod
    def _recent(tr: _PersonTrack, now: float, window: float) -> List[Tuple[float, float, float]]:
        return [(t, x, y) for (t, x, y) in tr.positions if now - t <= window]

    def _settled(self, tr: _PersonTrack, now: float, settle_sec: float, still_thr: float) -> bool:
        """Точка ног держится в пределах still_thr весь интервал settle_sec."""
        recent = self._recent(tr, now, settle_sec)
        if len(recent) < 2:
            return False
        # Требуем полное покрытие окна (иначе человек «сел» слишком рано).
        if now - recent[0][0] < settle_sec:
            return False
        cx = sum(x for _, x, _ in recent) / len(recent)
        cy = sum(y for _, _, y in recent) / len(recent)
        max_d = max(math.hypot(x - cx, y - cy) for _, x, y in recent)
        return max_d <= still_thr

    def _recent_centroid(self, tr: _PersonTrack, now: float, window: float) -> Tuple[float, float]:
        recent = self._recent(tr, now, window)
        if not recent:
            last = tr.positions[-1]
            return (last[1], last[2])
        cx = sum(x for _, x, _ in recent) / len(recent)
        cy = sum(y for _, _, y in recent) / len(recent)
        return (cx, cy)

    def _recent_start(self, tr: _PersonTrack, now: float, window: float) -> float:
        recent = self._recent(tr, now, window)
        return recent[0][0] if recent else now

    def cleanup(self, now: Optional[float] = None) -> int:
        """Удалить людей, не обновлявшихся дольше expiry_sec. Возвращает число."""
        if now is None:
            now = time.time()
        stale = [k for k, tr in self._tracks.items()
                 if now - tr.last_update > self._expiry_sec]
        for k in stale:
            del self._tracks[k]
        return len(stale)


def format_seated(seconds: float) -> str:
    """Секунды → 'MM:SS' (для бейджа на кадре и API)."""
    total = int(max(0.0, seconds))
    return f"{total // 60:02d}:{total % 60:02d}"
