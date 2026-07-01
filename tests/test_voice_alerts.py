"""Тесты курсорной доставки голосовых предупреждений в DetectionState.

Модель: алерты не извлекаются из общей очереди, а читаются «всё после курсора»
клиента (seq). Так несколько вкладок и несколько камер обслуживаются независимо,
без «съедания» алертов одним клиентом и без сериализации по одному на опрос.
"""


def test_first_poll_returns_cursor_without_backlog(state):
    # Накопился бэклог до подключения клиента.
    state.push_voice_alert("cam1", "тревога 1")
    res = state.get_voice_alerts_since(None)
    # Первый опрос (after=None) — только текущий курсор, без переигрывания бэклога.
    assert res["alerts"] == []
    assert res["cursor"] >= 1


def test_alerts_after_cursor_delivered(state):
    first = state.get_voice_alerts_since(None)
    cursor = first["cursor"]
    assert state.push_voice_alert("cam1", "тревога") is True
    res = state.get_voice_alerts_since(cursor)
    assert len(res["alerts"]) == 1
    assert res["alerts"][0]["text"] == "тревога"
    assert res["alerts"][0]["cam_id"] == "cam1"
    assert res["alerts"][0]["seq"] > cursor
    assert res["cursor"] > cursor


def test_cursor_advances_and_no_redelivery(state):
    base = state.get_voice_alerts_since(None)["cursor"]
    state.push_voice_alert("cam1", "первая")
    r1 = state.get_voice_alerts_since(base)
    assert len(r1["alerts"]) == 1
    # Повторный опрос с НОВЫМ курсором — алерт не приходит снова.
    r2 = state.get_voice_alerts_since(r1["cursor"])
    assert r2["alerts"] == []
    assert r2["cursor"] == r1["cursor"]


def test_multiple_clients_independent(state):
    # Два клиента с одинаковым курсором — оба получают алерт (нет «съедания»).
    base = state.get_voice_alerts_since(None)["cursor"]
    state.push_voice_alert("cam1", "общая")
    a = state.get_voice_alerts_since(base)
    b = state.get_voice_alerts_since(base)
    assert len(a["alerts"]) == 1
    assert len(b["alerts"]) == 1
    assert a["alerts"][0]["text"] == "общая"
    assert b["alerts"][0]["text"] == "общая"


def test_multiple_cameras_delivered_together(state):
    # Алерты с разных камер приходят одним списком (не по одному на опрос).
    base = state.get_voice_alerts_since(None)["cursor"]
    assert state.push_voice_alert("cam1", "зона 1") is True
    assert state.push_voice_alert("cam2", "зона 2") is True
    res = state.get_voice_alerts_since(base)
    texts = {a["text"] for a in res["alerts"]}
    assert texts == {"зона 1", "зона 2"}


def test_cooldown_per_camera_still_applies(state):
    base = state.get_voice_alerts_since(None)["cursor"]
    assert state.push_voice_alert("cam1", "раз") is True
    # Второй пуш на ту же камеру в пределах кулдауна — отброшен.
    assert state.push_voice_alert("cam1", "два") is False
    res = state.get_voice_alerts_since(base)
    assert len(res["alerts"]) == 1
    assert res["alerts"][0]["text"] == "раз"
