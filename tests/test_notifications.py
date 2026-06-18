"""Тесты очереди UI-уведомлений в DetectionState."""


def test_push_and_pop_notifications(state):
    assert state.pop_notifications() == []
    state.push_notification("granted", "ЖЕСТ «ОК» РАСПОЗНАН", "Иванов — доступ разрешён")
    state.push_notification("missing", "НЕ ХВАТАЕТ СИЗ", "Иванов: каска")
    items = state.pop_notifications()
    assert len(items) == 2
    assert items[0]["type"] == "granted"
    assert items[0]["title"] == "ЖЕСТ «ОК» РАСПОЗНАН"
    assert items[0]["sub"] == "Иванов — доступ разрешён"
    assert items[1]["type"] == "missing"
    # каждое уведомление имеет уникальный id и метку времени
    assert items[0]["id"] != items[1]["id"]
    assert "timestamp" in items[0]


def test_pop_clears_queue(state):
    state.push_notification("granted", "A")
    assert len(state.pop_notifications()) == 1
    # повторный pop — пусто (очередь очищена)
    assert state.pop_notifications() == []


def test_notification_default_sub(state):
    state.push_notification("warning", "Заголовок")
    item = state.pop_notifications()[0]
    assert item["sub"] == ""
