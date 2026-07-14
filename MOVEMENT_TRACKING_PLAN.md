# План: отслеживание перемещений людей (встал из-за стола / траектория / время на месте)

Задача: отслеживать, когда человек встал со своего места и куда пошёл, рисовать
траекторию движения на видео и считать, сколько он непрерывно сидит/находится на
своём месте.

## Подход (без новой ML-модели)

Используем уже существующие данные: детекции людей (`detected["persons"]`),
устойчивые `track_id` (ByteTrack) и `global_id` (Re-ID). Перемещение — чистая
геометрия по «точке ног» (низ-центр bbox), поэтому логика тестируема без кадров и
GPU (как `MotionDetector`/`DetectionState`).

**Идентификатор траектории:** `g{global_id}` если `global_id > 0` (переживает
переинициализацию трека и узнавание «со спины»), иначе `t{track_id}` (в режиме
«только люди», когда лица выключены). Один стабильный ключ на человека в пределах
камеры.

**Конечный автомат на человека** (масштаб порогов = рост bbox, поэтому не зависит
от разрешения и дистанции):
- `sitting` — точка ног держится у «якоря места» (anchor) в пределах допуска;
  копится непрерывное время `seated_seconds`.
- `moving` — сместился от якоря дальше порога «встал» → фиксируем событие «встал с
  места», рисуем траекторию ухода. Если снова замер в новой точке дольше
  `settle_sec` — там ставится новый якорь (сел на новое место).

## Чеклист реализации

### Бэкенд
- [x] `backend/tracking/__init__.py` + `backend/tracking/movement.py`:
      `MovementTracker` (по экземпляру на камеру). Чистая геометрия, пороги —
      живыми из `get_detection_setting` (hot-reload), с возможностью override в
      конструкторе (для тестов). Методы: `update(persons, now)` → список
      `MovementInfo` (state, seated_seconds, anchor, trail, just_stood_up,
      just_sat_down), `cleanup(now)` по TTL.
- [x] `backend/config.py`: добавить режим `"movement"` в `DETECT_MODES`;
      константы `MOVEMENT_*`; записи в `DETECTION_SETTINGS_SPEC` (группа
      «Отслеживание перемещений»): `movement_still_frac`, `movement_move_frac`,
      `movement_settle_sec`, `movement_trail_sec`.
- [x] `backend/core/state.py`: снапшот перемещений на камеру
      (`set_movement`/`get_movement`/`clear_movement`, под `_lock`), очистка в
      `clear_tracks`.
- [x] `backend/visualization/renderer.py`: `draw_trajectory`,
      `draw_seat_marker`, `draw_movement_badge` (бейдж «Сидит MM:SS» / «Идёт»).
- [x] `backend/main.py`: `_get_movement_tracker(cam_id)` (лениво, как
      `_get_motion_detector`), очистка `_movement_trackers` в `start_live`;
      интеграция в `process_frame` (собрать точки ног в основном цикле людей →
      `tracker.update` → отрисовка + `state.set_movement`). Гейт:
      `DETECT_MODES["people"] and DETECT_MODES["movement"]`. Работает и в режиме
      «только люди».
- [x] `backend/api/detection.py`: `"movement"` в цикле `api_set_detect_modes` +
      каскад «people off → movement off»; `GET /api/movement`.

### Тесты
- [x] `tests/test_movement.py`: установка якоря места, детекция «встал»,
      накопление `seated_seconds`, пересадка на новое место, обрезка следа по
      времени, cleanup по TTL, масштабирование порогов ростом.
- [x] `tests/test_state.py`: set/get/clear movement снапшота.

### Фронтенд
- [x] `frontend/src/api/client.ts` + `types.ts`: `getMovement()`, тип
      `MovementPerson`.
- [x] `Header.tsx`: тумблер режима «Перемещения» (+ каскад people-off).
- [x] `DispatcherPanel.tsx`: секция «ПЕРЕМЕЩЕНИЯ» — имя, статус (Сидит/Идёт),
      время на месте; лёгкий поллинг `/api/movement` при открытой панели.

### Финал
- [x] `python -m pytest tests/ -q` — зелёные.
- [x] `cd frontend && npm run build` — собирается.
- [x] Обновить `CLAUDE.md` (раздел про новый режим и модуль tracking).
- [x] Коммит + push в `claude/person-tracking-movement-hn8eth`.

## Ревью и правки (мультикамерность / идентичность)
- [x] **Миграция идентичности** (`_migrate_identity`): при распознавании лица ключ
      трека меняется `t{track_id}→g{global_id}` — состояние (место, время «сидит»,
      след) переносится, а не сбрасывается. Защита от переиспользования ByteTrack
      `track_id` (миграция только в `g…`). Кросс-окклюзия (новый `track_id`, тот
      же `global_id`) работает автоматически.
- [x] **Мультикамерность:** снапшот несёт `global_id` → фронт может сшить одного
      человека между камерами. Пространственные треки остаются по камере
      (координаты локальны; общий трекер по gid при перекрытии FOV → трэшинг).
- [x] `clear_movement()` + сброс трекеров в `stop_live` (нет устаревшего снапшота).
- [x] Дедуп `mkey` в кадре (два трека с одним global_id не плодят дубли/зигзаг).
- [x] Тесты: `TestIdentityMigration` (t→g перенос, g→g′, защита от reuse,
      кросс-окклюзия, отрицательный track_id).

## Кросс-камерный пространственный стич (cam1→cam2 одной линией)
- [x] `backend/tracking/floorplan.py`: гомография `homography_from_points`/
      `project_point` (чистый numpy DLT), `CameraProjector`, `validate_mapping`,
      `get_mapping`/`set_mapping` (калибровка в конфиге камеры, ключ `map_points`).
- [x] `state.py`: реестр треков карты `add_map_point`/`get_map_tracks`/
      `clear_map_tracks` по `global_id`, свой `_map_lock`.
- [x] `main.py`: кэш `_projectors` + `_get_projector`/`invalidate_projector`;
      проекция точки ног опознанных людей в координаты карты в `process_frame`
      (отброс точек за планом); очистка в start/stop.
- [x] `config.py`: настройка `movement_map_trail_sec`.
- [x] API: `GET/PUT /api/cameras/<id>/mapping` (cameras.py),
      `GET /api/movement/tracks` (detection.py).
- [x] Фронт: `MapPage` (`/map`) — живая мини-карта со сшитыми линиями +
      калибратор (≥4 пар «кадр↔карта»); навигация «КАРТА» в Header; типы+client.
- [x] Тесты: `test_floorplan.py` (гомография, **кросс-камерная согласованность**:
      одна физическая точка с двух камер → одна точка карты, валидация,
      проектор) + `TestMapTracks` в `test_state.py`.
- [x] Итог: 515 passed, фронт собирается; CLAUDE.md §2.6.1/2.9/2.12/3.
</content>
</invoke>
