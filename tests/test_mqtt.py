"""Тесты MQTT-публикатора (мягкая деградация без брокера/paho)."""
import importlib

import backend.mqtt.publisher as pub_mod
from backend.mqtt.publisher import MqttPublisher, get_publisher


def test_publisher_disabled_returns_none(monkeypatch):
    import backend.config as cfg
    monkeypatch.setattr(cfg, "MQTT_ENABLED", False)
    pub_mod._publisher = None
    assert get_publisher() is None


def test_publisher_methods_are_noop_without_client(monkeypatch):
    # Эмулируем отсутствие paho: клиент не создаётся, методы не падают.
    p = MqttPublisher.__new__(MqttPublisher)
    p.prefix = "frigate"
    p._client = None
    p._connected = False
    # Ни один вызов не должен бросить исключение.
    p.publish_motion("cam1", True, 0.5)
    p.publish_detection("cam1", 2, 1, 0, "нарушение")
    p.publish_violation("cam1", "Иванов", 5, ["каска"])
    p.publish_approved("cam1", "Иванов", 5)
    p.publish_heartbeat({"ts": 1.0})
    p.close()
    assert p.connected is False


def test_publish_serializes_dict(monkeypatch):
    captured = {}

    class FakeClient:
        def publish(self, topic, payload, retain=False):
            captured["topic"] = topic
            captured["payload"] = payload
            captured["retain"] = retain

    p = MqttPublisher.__new__(MqttPublisher)
    p.prefix = "frigate"
    p._client = FakeClient()
    p._connected = True
    p.publish_motion("cam1", True, 0.25)
    assert captured["topic"] == "frigate/cam1/motion"
    assert '"motion": true' in captured["payload"]
    assert '"area_ratio": 0.25' in captured["payload"]


def test_get_publisher_singleton(monkeypatch):
    import backend.config as cfg
    monkeypatch.setattr(cfg, "MQTT_ENABLED", True)
    monkeypatch.setattr(cfg, "MQTT_HOST", "localhost")
    monkeypatch.setattr(cfg, "MQTT_PORT", 1883)
    monkeypatch.setattr(cfg, "MQTT_USER", "")
    monkeypatch.setattr(cfg, "MQTT_PASSWORD", "")
    monkeypatch.setattr(cfg, "MQTT_TOPIC_PREFIX", "frigate")
    monkeypatch.setattr(cfg, "MQTT_HA_DISCOVERY", False)
    pub_mod._publisher = None
    p1 = get_publisher()
    p2 = get_publisher()
    assert p1 is p2
    # Очистка singleton, чтобы не течь в другие тесты.
    if p1 is not None:
        p1.close()
    pub_mod._publisher = None
