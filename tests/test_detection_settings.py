"""Тесты рантайм-настроек детекции (config.DETECTION_SETTINGS + хелперы).

Запись на диск мокается, а сам словарь снапшотится/восстанавливается — тесты не
пишут в data/ и не протекают друг в друга.
"""
import pytest
import backend.config as config


@pytest.fixture
def settings_sandbox(monkeypatch):
    # Не трогаем реальный data/detection_settings.json.
    monkeypatch.setattr(config, "save_detection_settings", lambda: None)
    snapshot = dict(config.DETECTION_SETTINGS)
    yield
    config.DETECTION_SETTINGS.clear()
    config.DETECTION_SETTINGS.update(snapshot)


def test_defaults_match_constants():
    s = config.DETECTION_SETTINGS
    assert s["person_conf"] == config.CONF_THRESH
    assert s["ppe_conf"] == config.PPE_CONF_THRESH
    assert s["min_cones"] == config.MIN_CONES
    assert s["zone_expand_px"] == config.ZONE_EXPAND_PX
    assert s["ppe_top_ratio"] == config.TOP_RATIO
    assert s["approval_duration"] == config.APPROVAL_DURATION
    assert s["gesture_cooldown"] == config.GESTURE_COOLDOWN
    assert s["voice_alert_cooldown"] == config.VOICE_ALERT_COOLDOWN


def test_spec_keys_cover_settings():
    spec_keys = {s["key"] for s in config.DETECTION_SETTINGS_SPEC}
    assert spec_keys == set(config.DETECTION_SETTINGS)
    # У каждой записи спеки есть поля для UI и валидации.
    for s in config.DETECTION_SETTINGS_SPEC:
        for field in ("default", "type", "min", "max", "step", "group", "label", "desc"):
            assert field in s, f"{s['key']} без {field}"
        assert s["type"] in ("int", "float")


def test_get_detection_setting_live(settings_sandbox):
    config.update_detection_settings({"person_conf": 0.5})
    assert config.get_detection_setting("person_conf") == 0.5


def test_update_clamps_above_max(settings_sandbox):
    res = config.update_detection_settings({"person_conf": 5.0})  # max 0.95
    assert res["person_conf"] == 0.95


def test_update_clamps_below_min(settings_sandbox):
    res = config.update_detection_settings({"voice_alert_cooldown": -10})  # min 0.0
    assert res["voice_alert_cooldown"] == 0.0


def test_int_setting_coerced_and_rounded(settings_sandbox):
    res = config.update_detection_settings({"min_cones": 4.6})
    assert res["min_cones"] == 5
    assert isinstance(res["min_cones"], int)


def test_unknown_key_ignored(settings_sandbox):
    before = dict(config.DETECTION_SETTINGS)
    res = config.update_detection_settings({"nope": 1, "person_conf": 0.6})
    assert "nope" not in res
    assert res["person_conf"] == 0.6
    assert set(res) == set(before)


def test_garbage_value_ignored(settings_sandbox):
    res = config.update_detection_settings({"person_conf": "abc"})
    assert res["person_conf"] == config.CONF_THRESH  # не изменилось


def test_partial_update_keeps_others(settings_sandbox):
    config.update_detection_settings({"min_cones": 6})
    res = config.update_detection_settings({"zone_expand_px": 40})
    assert res["min_cones"] == 6        # прежнее сохранилось
    assert res["zone_expand_px"] == 40
