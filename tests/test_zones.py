"""Тесты пользовательских полигональных зон (редактор зон)."""
import pytest

import backend.zones as zones_mod
from backend.zones import (
    validate_zone, person_in_zone, in_any_danger_zone, box_in_mask,
    apply_masks, has_danger_zones, to_pixels, required_ppe,
    get_zones, set_zones, add_zone, update_zone, delete_zone,
)

# Квадрат в нормализованных координатах: x∈[0.1,0.5], y∈[0.1,0.5]
SQUARE = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
W = H = 1000


# ── validate_zone ───────────────────────────────────────────
def test_validate_zone_ok():
    z = validate_zone({"type": "danger", "points": SQUARE, "name": "Зона1",
                       "require_ppe": ["helmet", "vest", "bogus"]})
    assert z["type"] == "danger"
    assert z["name"] == "Зона1"
    assert z["require_ppe"] == ["helmet", "vest"]  # bogus отфильтрован
    assert len(z["id"]) > 0
    assert len(z["points"]) == 4


def test_validate_zone_generates_id_and_default_name():
    z = validate_zone({"type": "mask", "points": SQUARE})
    assert z["id"]
    assert z["name"] == "mask"


def test_validate_zone_bad_type():
    with pytest.raises(ValueError):
        validate_zone({"type": "wormhole", "points": SQUARE})


def test_validate_zone_too_few_points():
    with pytest.raises(ValueError):
        validate_zone({"type": "danger", "points": [[0.1, 0.1], [0.5, 0.5]]})


def test_validate_zone_clamps_coords():
    z = validate_zone({"type": "danger", "points": [[-1, 0.1], [2, 0.1], [0.5, 2]]})
    for x, y in z["points"]:
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


# ── Геометрия ───────────────────────────────────────────────
def _zone(t="danger", pts=SQUARE):
    return {"id": "z1", "name": t, "type": t, "points": pts, "require_ppe": []}


def test_person_in_zone_inside():
    # foot = (300, 490) → норм (0.30, 0.49) внутри квадрата
    assert person_in_zone([250, 100, 350, 490], _zone(), W, H) is True


def test_person_in_zone_outside():
    assert person_in_zone([800, 100, 900, 900], _zone(), W, H) is False


def test_in_any_danger_zone_includes_restricted():
    assert in_any_danger_zone([250, 100, 350, 490], [_zone("restricted")], W, H) is True
    # mask-зона не считается опасной
    assert in_any_danger_zone([250, 100, 350, 490], [_zone("mask")], W, H) is False


def test_has_danger_zones():
    assert has_danger_zones([_zone("danger")]) is True
    assert has_danger_zones([_zone("mask")]) is False


def test_box_in_mask():
    # центр (300,300) → норм 0.3 внутри маски
    assert box_in_mask([250, 250, 350, 350], [_zone("mask")], W, H) is True
    assert box_in_mask([800, 800, 900, 900], [_zone("mask")], W, H) is False
    # danger-зона маской не считается
    assert box_in_mask([250, 250, 350, 350], [_zone("danger")], W, H) is False


def test_apply_masks_filters_persons_and_items():
    detected = {
        "persons": [[250, 250, 350, 350], [800, 800, 900, 900]],
        "person_track_ids": [11, 22],
        "helmets": [[260, 260, 300, 300]],   # в маске
        "masks": [], "vests": [], "cones": [[810, 810, 850, 850]],  # вне маски
    }
    out = apply_masks(detected, [_zone("mask")], W, H)
    assert out["persons"] == [[800, 800, 900, 900]]
    assert out["person_track_ids"] == [22]
    assert out["helmets"] == []         # удалён (в маске)
    assert out["cones"] == [[810, 810, 850, 850]]  # сохранён


def test_apply_masks_noop_without_mask_zones():
    detected = {"persons": [[1, 1, 2, 2]], "person_track_ids": [1],
                "helmets": [], "masks": [], "vests": [], "cones": []}
    out = apply_masks(detected, [_zone("danger")], W, H)
    assert out["persons"] == [[1, 1, 2, 2]]


def test_to_pixels():
    px = to_pixels(_zone(), 1000, 1000)
    assert px[0] == (100, 100)
    assert px[2] == (500, 500)


# ── Пер-зонные требования СИЗ ───────────────────────────────
INSIDE = [250, 100, 350, 490]   # foot норм (0.30, 0.49) — внутри SQUARE
OUTSIDE = [800, 100, 900, 900]  # foot норм (0.85, 0.90) — вне SQUARE
DEFAULT = ["helmet", "mask", "vest"]


def test_required_ppe_default_outside_zones():
    # Вне любых зон — глобальный дефолт.
    assert required_ppe(OUTSIDE, [], W, H, DEFAULT) == {"helmet", "mask", "vest"}


def test_required_ppe_zone_overrides():
    z = {**_zone("danger"), "require_ppe": ["mask"]}
    # Внутри зоны — только её требование (каска/жилет не нужны).
    assert required_ppe(INSIDE, [z], W, H, DEFAULT) == {"mask"}
    # Снаружи — дефолт.
    assert required_ppe(OUTSIDE, [z], W, H, DEFAULT) == {"helmet", "mask", "vest"}


def test_required_ppe_empty_zone_inherits_default():
    # Зона с пустым require_ppe наследует глобальный дефолт (не «беззубая»).
    z = {**_zone("danger"), "require_ppe": []}
    assert required_ppe(INSIDE, [z], W, H, DEFAULT) == {"helmet", "mask", "vest"}
    # Если глобальный дефолт пуст (демо без СИЗ) — внутри тоже ничего не нужно.
    assert required_ppe(INSIDE, [z], W, H, []) == set()


def test_required_ppe_union_of_overlapping_zones():
    z1 = {**_zone("danger"), "require_ppe": ["helmet"]}
    z2 = {**_zone("restricted"), "require_ppe": ["vest"]}
    assert required_ppe(INSIDE, [z1, z2], W, H, DEFAULT) == {"helmet", "vest"}


def test_required_ppe_empty_default_relaxes_everywhere():
    # PPE_REQUIRED_DEFAULT="" → СИЗ не требуются нигде вне зон.
    assert required_ppe(OUTSIDE, [], W, H, []) == set()


# ── CRUD (конфиг в памяти) ──────────────────────────────────
@pytest.fixture
def mem_config(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(zones_mod, "get_camera_config", lambda cam: store.setdefault(cam, {}))

    def _set(cam, **kw):
        store.setdefault(cam, {}).update(kw)
    monkeypatch.setattr(zones_mod, "set_camera_config", _set)
    return store


def test_crud_add_get_update_delete(mem_config):
    assert get_zones("cam1") == []
    z = add_zone("cam1", {"type": "danger", "points": SQUARE, "name": "A"})
    assert len(get_zones("cam1")) == 1
    zid = z["id"]
    upd = update_zone("cam1", zid, {"name": "B", "type": "restricted"})
    assert upd["name"] == "B" and upd["type"] == "restricted"
    assert update_zone("cam1", "nope", {"name": "X"}) is None
    assert delete_zone("cam1", zid) is True
    assert delete_zone("cam1", zid) is False
    assert get_zones("cam1") == []


def test_set_zones_replaces(mem_config):
    set_zones("cam1", [{"type": "danger", "points": SQUARE},
                       {"type": "mask", "points": SQUARE}])
    assert len(get_zones("cam1")) == 2


def test_set_zones_rejects_invalid(mem_config):
    with pytest.raises(ValueError):
        set_zones("cam1", [{"type": "danger", "points": [[0, 0]]}])
