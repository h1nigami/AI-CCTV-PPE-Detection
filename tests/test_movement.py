"""Тесты трекера перемещений (backend/tracking/movement.py).

Пороги задаём явно в конструкторе (hermetic, без рантайм-настроек), время —
явными таймстампами в update(now=...), поэтому кадры/GPU не нужны.
"""
import pytest
from backend.tracking.movement import MovementTracker, format_seated


# Стандартный трекер: рост человека 200px → still_thr=30px, move_thr=120px.
def _tracker(**kw):
    params = dict(still_frac=0.15, move_frac=0.6, settle_sec=2.0,
                  trail_sec=15.0, expiry_sec=60.0)
    params.update(kw)
    return MovementTracker(**params)


def _box(cx, top=100, height=200, width=200):
    """bbox с точкой ног (cx, top+height): foot_x=cx, foot_y=top+height."""
    return (cx - width / 2, top, cx + width / 2, top + height)


def _feed(tr, key, cx, times, name=""):
    """Прогнать серию кадров с человеком в точке cx на моменты times."""
    last = None
    for t in times:
        last = tr.update([{"key": key, "box": _box(cx), "name": name}], now=t)[0]
    return last


class TestSitDown:
    def test_not_settled_before_settle_sec(self):
        tr = _tracker()
        info = _feed(tr, "p1", 200, [0.0, 0.5, 1.0, 1.5])
        assert info.state == "moving"
        assert info.anchor is None
        assert info.seated_seconds == 0.0

    def test_settles_after_settle_sec(self):
        tr = _tracker()
        info = _feed(tr, "p1", 200, [0.0, 0.5, 1.0, 1.5, 2.0])
        assert info.state == "sitting"
        assert info.anchor is not None
        assert info.just_sat_down is True
        # foot_x=200, foot_y=300
        assert abs(info.anchor[0] - 200) < 1 and abs(info.anchor[1] - 300) < 1

    def test_seated_seconds_accumulate(self):
        tr = _tracker()
        _feed(tr, "p1", 200, [0.0, 0.5, 1.0, 1.5, 2.0])
        info = _feed(tr, "p1", 200, [2.5, 3.0])
        assert info.state == "sitting"
        # сидит с t≈0.0, на t=3.0 → ~3 сек
        assert info.seated_seconds == pytest.approx(3.0, abs=0.01)


class TestStandUp:
    def test_stands_up_when_moving_far(self):
        tr = _tracker()
        _feed(tr, "p1", 200, [0.0, 0.5, 1.0, 1.5, 2.0])  # сел у 200
        # move_thr=120; сдвиг на 200px (в точку 400) → встал
        info = tr.update([{"key": "p1", "box": _box(400)}], now=2.5)[0]
        assert info.state == "moving"
        assert info.just_stood_up is True
        assert info.seated_seconds == 0.0

    def test_small_jitter_keeps_sitting(self):
        tr = _tracker()
        _feed(tr, "p1", 200, [0.0, 0.5, 1.0, 1.5, 2.0])
        # сдвиг на 20px (< still_thr 30) → всё ещё сидит
        info = tr.update([{"key": "p1", "box": _box(220)}], now=2.5)[0]
        assert info.state == "sitting"
        assert info.just_stood_up is False

    def test_medium_move_below_threshold_keeps_sitting(self):
        tr = _tracker()
        _feed(tr, "p1", 200, [0.0, 0.5, 1.0, 1.5, 2.0])
        # сдвиг на 100px (> still 30, но < move 120) → пока сидит (не встал)
        info = tr.update([{"key": "p1", "box": _box(300)}], now=2.5)[0]
        assert info.state == "sitting"


class TestReSeat:
    def test_resits_at_new_location(self):
        tr = _tracker()
        _feed(tr, "p1", 200, [0.0, 0.5, 1.0, 1.5, 2.0])   # сел у 200
        tr.update([{"key": "p1", "box": _box(600)}], now=2.5)  # встал/пошёл
        # замер у новой точки 600 на 2+ сек → новый якорь
        info = _feed(tr, "p1", 600, [3.0, 3.5, 4.0, 4.5, 5.0])
        assert info.state == "sitting"
        assert abs(info.anchor[0] - 600) < 1


class TestScaleByHeight:
    def test_threshold_scales_with_person_height(self):
        # Один и тот же сдвиг 150px: у мелкого (h=200, move_thr=120) → встал,
        # у крупного (h=600, move_thr=360) → всё ещё сидит.
        small = _tracker()
        for t in [0.0, 0.5, 1.0, 1.5, 2.0]:
            small.update([{"key": "s", "box": _box(200, height=200)}], now=t)
        s_info = small.update([{"key": "s", "box": _box(350, height=200)}], now=2.5)[0]
        assert s_info.state == "moving"

        big = _tracker()
        for t in [0.0, 0.5, 1.0, 1.5, 2.0]:
            big.update([{"key": "b", "box": _box(200, height=600)}], now=t)
        b_info = big.update([{"key": "b", "box": _box(350, height=600)}], now=2.5)[0]
        assert b_info.state == "sitting"


class TestTrail:
    def test_trail_pruned_by_time(self):
        tr = _tracker(trail_sec=5.0)
        # 20 кадров через 1 сек — след старше 5 сек обрезается
        times = [float(i) for i in range(20)]
        info = None
        for t in times:
            # слегка двигаемся, чтобы точки отличались
            info = tr.update([{"key": "p1", "box": _box(200 + int(t))}], now=t)[0]
        # старейшая точка следа не старше trail_sec (с запасом на min-2 правило)
        assert len(info.trail) <= 7

    def test_trail_keeps_min_two_points(self):
        tr = _tracker(trail_sec=0.001)
        tr.update([{"key": "p1", "box": _box(200)}], now=0.0)
        info = tr.update([{"key": "p1", "box": _box(210)}], now=100.0)[0]
        assert len(info.trail) >= 2


class TestCleanup:
    def test_stale_person_removed(self):
        tr = _tracker(expiry_sec=10.0)
        tr.update([{"key": "p1", "box": _box(200)}], now=0.0)
        assert "p1" in tr._tracks
        # следующий кадр другого человека сильно позже → p1 вычищается
        tr.update([{"key": "p2", "box": _box(400)}], now=100.0)
        assert "p1" not in tr._tracks
        assert "p2" in tr._tracks

    def test_recent_person_kept(self):
        tr = _tracker(expiry_sec=10.0)
        tr.update([{"key": "p1", "box": _box(200)}], now=0.0)
        tr.update([{"key": "p2", "box": _box(400)}], now=5.0)
        assert "p1" in tr._tracks and "p2" in tr._tracks


class TestMultiplePeople:
    def test_independent_states(self):
        tr = _tracker()
        for t in [0.0, 0.5, 1.0, 1.5, 2.0]:
            tr.update([
                {"key": "a", "box": _box(200)},
                {"key": "b", "box": _box(800)},
            ], now=t)
        infos = tr.update([
            {"key": "a", "box": _box(200)},      # сидит
            {"key": "b", "box": _box(1100)},     # встал (сдвиг 300 > 120)
        ], now=2.5)
        by_key = {i.key: i for i in infos}
        assert by_key["a"].state == "sitting"
        assert by_key["b"].state == "moving"


class TestFormatSeated:
    def test_format(self):
        assert format_seated(0) == "00:00"
        assert format_seated(5) == "00:05"
        assert format_seated(65) == "01:05"
        assert format_seated(3661) == "61:01"

    def test_negative_clamped(self):
        assert format_seated(-5) == "00:00"


class TestIdentityMigration:
    """При распознавании личности ключ трека меняется t{track_id}→g{global_id};
    накопленное состояние (место, время «сидит», след) должно переноситься, а не
    сбрасываться (иначе таймер обнулялся бы в момент, когда поймали лицо)."""

    def test_t_to_g_preserves_seated_time(self):
        tr = _tracker()
        # Человек сидит спиной (лица нет) → ключ t7, track_id=7.
        info = None
        for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
            info = tr.update([{"key": "t7", "track_id": 7, "box": _box(200)}], now=t)[0]
        assert info.state == "sitting"
        assert info.seated_seconds == pytest.approx(2.5, abs=0.05)
        # Повернулся — лицо распозналось: тот же track_id 7, ключ стал g5.
        info = tr.update([{"key": "g5", "track_id": 7, "box": _box(200)}], now=3.0)[0]
        assert info.state == "sitting"                 # не сбросилось в moving
        assert info.seated_seconds == pytest.approx(3.0, abs=0.05)  # таймер продолжился
        assert "g5" in tr._tracks and "t7" not in tr._tracks

    def test_g_to_g_correction_migrates(self):
        tr = _tracker()
        for t in [0.0, 0.5, 1.0, 1.5, 2.0]:
            tr.update([{"key": "g5", "track_id": 7, "box": _box(200)}], now=t)
        info = tr.update([{"key": "g8", "track_id": 7, "box": _box(200)}], now=2.5)[0]
        assert info.state == "sitting"
        assert info.seated_seconds == pytest.approx(2.5, abs=0.05)
        assert "g8" in tr._tracks and "g5" not in tr._tracks

    def test_track_id_reuse_does_not_steal_seat(self):
        # g5 сидит на track 7. Затем track 7 переиспользован ByteTrack под НОВОГО
        # неопознанного человека (ключ t7) — он НЕ должен украсть место g5.
        tr = _tracker()
        for t in [0.0, 0.5, 1.0, 1.5, 2.0]:
            tr.update([{"key": "g5", "track_id": 7, "box": _box(200)}], now=t)
        info = tr.update([{"key": "t7", "track_id": 7, "box": _box(900)}], now=2.5)[0]
        assert info.key == "t7"
        assert info.state == "moving"          # свежий трек, места ещё нет
        assert "g5" in tr._tracks              # место g5 не украдено

    def test_cross_occlusion_same_gid_continues(self):
        # Один global_id на РАЗНЫХ track_id (окклюзия сменила id) → та же личность,
        # время «сидит» продолжается (ключ g5 общий).
        tr = _tracker()
        for t in [0.0, 0.5, 1.0, 1.5, 2.0]:
            tr.update([{"key": "g5", "track_id": 7, "box": _box(200)}], now=t)
        info = tr.update([{"key": "g5", "track_id": 12, "box": _box(200)}], now=2.5)[0]
        assert info.state == "sitting"
        assert info.seated_seconds == pytest.approx(2.5, abs=0.05)

    def test_negative_track_id_not_migrated(self):
        # Отрицательный track_id (нетрекнутый fallback) не участвует в миграции.
        tr = _tracker()
        tr.update([{"key": "t-1", "track_id": -1, "box": _box(200)}], now=0.0)
        assert -1 not in tr._track_key


class TestName:
    def test_name_retained_when_missing_later(self):
        tr = _tracker()
        tr.update([{"key": "p1", "box": _box(200), "name": "Иван"}], now=0.0)
        # позже имя не пришло — прежнее сохраняется
        info = tr.update([{"key": "p1", "box": _box(200), "name": ""}], now=0.5)[0]
        assert info.name == "Иван"
