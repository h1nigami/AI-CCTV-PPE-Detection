"""MQTT-шина событий — публикация детекций/нарушений/heartbeat в брокер.

Ключевое арх-решение плана: MQTT как центральная шина для слабого связывания
компонентов и интеграции с Home Assistant. Брокер (eclipse-mosquitto) уже описан
в docker-compose.yml; здесь — клиент-публикатор.

Реализация НЕОБЯЗАТЕЛЬНА и деградирует мягко: если `paho-mqtt` не установлен,
MQTT выключен в конфиге или брокер недоступен — публикация превращается в no-op,
основной пайплайн не падает. Подключение в фоне (loop_start), без блокировки.

Топики (префикс настраивается, по умолчанию `frigate`):
    <prefix>/<cam>/motion         движение обнаружено
    <prefix>/<cam>/detection      сводка детекции (люди/СИЗ)
    <prefix>/<cam>/violation      нарушение
    <prefix>/<cam>/approved       выдан пропуск
    <prefix>/system/heartbeat     heartbeat процесса
"""
from __future__ import annotations
import json
import threading
import time
from typing import Optional


class MqttPublisher:
    def __init__(self, host: str, port: int = 1883, prefix: str = "frigate",
                 user: str = "", password: str = "", ha_discovery: bool = False):
        self.host = host
        self.port = int(port)
        self.prefix = prefix.rstrip("/")
        self.ha_discovery = ha_discovery
        self._client = None
        self._connected = False
        self._lock = threading.Lock()
        try:
            import paho.mqtt.client as mqtt  # noqa: WPS433
        except Exception as exc:  # paho не установлен
            print(f"[MQTT] paho-mqtt недоступен ({exc}); публикация отключена")
            return
        try:
            self._client = mqtt.Client()
            if user:
                self._client.username_pw_set(user, password)
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            # Last Will: при разрыве брокер сам опубликует offline-статус.
            self._client.will_set(f"{self.prefix}/system/status", "offline", retain=True)
            self._client.connect_async(self.host, self.port, keepalive=30)
            self._client.loop_start()
            print(f"[MQTT] Подключение к {self.host}:{self.port} (prefix={self.prefix})")
        except Exception as exc:
            print(f"[MQTT] Не удалось инициализировать клиент: {exc}")
            self._client = None

    # ── Колбэки соединения ──────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc, *args):
        self._connected = (rc == 0)
        if self._connected:
            print("[MQTT] Подключено к брокеру")
            try:
                client.publish(f"{self.prefix}/system/status", "online", retain=True)
                if self.ha_discovery:
                    self._publish_discovery()
            except Exception:
                pass
        else:
            print(f"[MQTT] Отказ подключения, rc={rc}")

    def _on_disconnect(self, client, userdata, rc, *args):
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Публикация ──────────────────────────────────────────────
    def _publish(self, topic: str, payload, retain: bool = False):
        if self._client is None:
            return
        try:
            if not isinstance(payload, (str, bytes)):
                payload = json.dumps(payload, ensure_ascii=False)
            self._client.publish(topic, payload, retain=retain)
        except Exception as exc:
            print(f"[MQTT] Ошибка публикации {topic}: {exc}")

    def publish_motion(self, cam_id: str, motion: bool, area_ratio: float = 0.0):
        self._publish(f"{self.prefix}/{cam_id}/motion",
                      {"motion": bool(motion), "area_ratio": round(area_ratio, 4),
                       "ts": time.time()})

    def publish_detection(self, cam_id: str, people: int, violations: int,
                          approved: int, category: str):
        self._publish(f"{self.prefix}/{cam_id}/detection",
                      {"people": people, "violations": violations,
                       "approved": approved, "category": category, "ts": time.time()})

    def publish_violation(self, cam_id: str, person_name: str = "",
                          person_id: int = 0, missing: Optional[list] = None):
        self._publish(f"{self.prefix}/{cam_id}/violation",
                      {"person_name": person_name, "person_id": person_id,
                       "missing": missing or [], "ts": time.time()})

    def publish_approved(self, cam_id: str, person_name: str = "", person_id: int = 0):
        self._publish(f"{self.prefix}/{cam_id}/approved",
                      {"person_name": person_name, "person_id": person_id, "ts": time.time()})

    def publish_heartbeat(self, payload: Optional[dict] = None):
        self._publish(f"{self.prefix}/system/heartbeat",
                      payload or {"ts": time.time()})

    # ── Home Assistant MQTT Discovery ───────────────────────────
    def _publish_discovery(self):
        """Публикует конфиги сущностей для авто-обнаружения в Home Assistant."""
        from backend.config import CAMERAS
        device = {
            "identifiers": ["kontroler_ai"],
            "name": "Kontroler AI PPE Detection",
            "model": "AI CCTV PPE",
            "manufacturer": "KONTROLER AI",
        }
        for cam_id in list(CAMERAS.keys()):
            base = f"homeassistant"
            # Бинарный сенсор движения
            self._publish(
                f"{base}/binary_sensor/kontroler_{cam_id}_motion/config",
                {"name": f"{cam_id} Motion", "unique_id": f"kontroler_{cam_id}_motion",
                 "state_topic": f"{self.prefix}/{cam_id}/motion",
                 "value_template": "{{ 'ON' if value_json.motion else 'OFF' }}",
                 "payload_on": "ON", "payload_off": "OFF",
                 "device_class": "motion", "device": device},
                retain=True)
            # Сенсор количества людей
            self._publish(
                f"{base}/sensor/kontroler_{cam_id}_people/config",
                {"name": f"{cam_id} People", "unique_id": f"kontroler_{cam_id}_people",
                 "state_topic": f"{self.prefix}/{cam_id}/detection",
                 "value_template": "{{ value_json.people }}", "device": device},
                retain=True)
            # Сенсор нарушений
            self._publish(
                f"{base}/sensor/kontroler_{cam_id}_violations/config",
                {"name": f"{cam_id} Violations", "unique_id": f"kontroler_{cam_id}_violations",
                 "state_topic": f"{self.prefix}/{cam_id}/detection",
                 "value_template": "{{ value_json.violations }}", "device": device},
                retain=True)

    def close(self):
        if self._client is not None:
            try:
                self._client.publish(f"{self.prefix}/system/status", "offline", retain=True)
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._connected = False


_publisher: Optional[MqttPublisher] = None
_pub_lock = threading.Lock()


def get_publisher() -> Optional[MqttPublisher]:
    """Синглтон публикатора. None, если MQTT выключен в конфиге."""
    global _publisher
    if _publisher is not None:
        return _publisher
    from backend.config import (
        MQTT_ENABLED, MQTT_HOST, MQTT_PORT, MQTT_TOPIC_PREFIX,
        MQTT_USER, MQTT_PASSWORD, MQTT_HA_DISCOVERY,
    )
    if not MQTT_ENABLED:
        return None
    with _pub_lock:
        if _publisher is None:
            _publisher = MqttPublisher(
                host=MQTT_HOST, port=MQTT_PORT, prefix=MQTT_TOPIC_PREFIX,
                user=MQTT_USER, password=MQTT_PASSWORD,
                ha_discovery=MQTT_HA_DISCOVERY,
            )
    return _publisher
