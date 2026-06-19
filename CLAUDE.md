# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Система видеоаналитики реального времени для контроля СИЗ (каски/маски/жилеты), опасных зон, Re-ID лиц и распознавания жестов на базе YOLOv8 + InsightFace. Flask-бэкенд (Waitress WSGI) раздаёт собранный React/Vite-фронтенд и MJPEG-стримы. Весь код и комментарии — на русском; придерживаться того же.

---

## 1. Команды

### Тесты
```bash
python -m pytest tests/ -v                         # все тесты (87 шт.)
python -m pytest tests/test_engine.py -v           # один файл
python -m pytest tests/test_gallery.py::TestMatchOrRegister -v        # один класс
python -m pytest tests/test_state.py::test_name -v # один тест
python -m pytest tests/ --cov=backend              # с покрытием
```
- Тесты мокают YOLO/InsightFace (`tests/conftest.py`), GPU/камеры/сеть не нужны. Запускать из корня репо.
- Покрытие: `test_engine.py` (детекция/зоны), `test_gallery.py` (Re-ID, адаптивный порог, merge), `test_state.py` (DetectionState), `test_config.py` (конфиг, CLASS_NAMES).

### Локальный запуск
```bash
pip install -r requirements.txt
python app.py [PORT]          # бэкенд на :8000 (Waitress); раздаёт frontend/dist если собран
cd frontend && npm install
cd frontend && npm run dev     # дев-фронт :5173, проксирует API на VITE_API_TARGET (по умолч. 192.168.0.97:8000)
cd frontend && npm run build   # tsc -b + vite build → frontend/dist (прод раздаёт Flask)
cd frontend && npm run preview # предпросмотр прод-сборки
```
**Важно:** в проде Flask раздаёт статику из `frontend/dist` (см. `serve_frontend` в `backend/app.py`), а не дев-сервер. После правок React обязателен `npm run build`.

### Docker
```bash
docker compose --profile cpu up --build -d     # CPU (default) + MinIO + MQTT + createbuckets
docker compose --profile gpu up --build -d     # NVIDIA CUDA
docker compose --profile cpu restart app-cpu   # после правок Python (bind-mount, без пересборки)
docker compose --profile cpu logs -f app-cpu
```
- `docker-compose.override.yml` (dev, применяется автоматически) bind-маунтит код и **прогоняет pytest перед стартом** (`pytest tests/ && python app.py`), плюс ставит FLASK_DEBUG=1.
- После правок Python достаточно `restart` (код примонтирован). После правок React — `npm run build` + `restart`.
- Dockerfile'ы: `Dockerfile` (CPU multi-stage), `Dockerfile.gpu` (CUDA), `Dockerfile.jetson` (ARM/Jetson), `Dockerfile.frontend` (nginx как reverse-proxy для отдельного фронт-сервера, `docker-compose.frontend.yml`, env `BACKEND_URL`).
- Полный чеклист деплоя бэка на GPU-сервер + фронта отдельным контейнером — `DEPLOY_FRONTEND_CHECKLIST.md`.

### Деплой на серверы (бэк + фронт раздельно)
```bash
./deploy.sh backend            # код бэка → бэк-сервер + restart app-gpu (bind-mount, быстро)
./deploy.sh backend --build    # то же + пересборка образа (после правок зависимостей/Dockerfile)
./deploy.sh frontend           # фронт → фронт-сервер + пересборка nginx-образа
./deploy.sh all                # оба
.\deploy.ps1 all               # то же из Windows PowerShell (обёртка ищет Git Bash, НЕ WSL)
```
- **Источник истины — локальный рабочий каталог** (то, что закоммичено). `deploy.sh` переносит код по ssh (tar-туннель), НЕ зависит от git на серверах. **Модели/`data` не переносятся** — на новый бэк-сервер `models/buffalo_l/` и `data/` доставить вручную один раз.
- **Все адреса серверов — в `deploy.env`** (`BACKEND_HOST`, `FRONTEND_HOST`, каталоги, `BACKEND_URL`). Правится в ОДНОМ месте; читается и `deploy.sh` (source), и `docker-compose.frontend.yml` (`env_file` → `BACKEND_URL` внутрь nginx-контейнера).
- **Авто-деплой**: git-хук `scripts/git-hooks/pre-push` запускает `deploy.sh all` при `git push` в `main`. Подключение (один раз): `git config core.hooksPath scripts/git-hooks`. Пропуск: `SKIP_DEPLOY=1 git push` или `git push --no-verify`. Хук не блокирует push при недоступности серверов.
- Связь фронт↔бэк: nginx на фронт-сервере раздаёт собранный фронт и `proxy_pass` на `${BACKEND_URL}` для `/api`, `/video_frame`, `/video_feed`, `/start`, `/stop`, `/cameras`, `/detection_log`, `/export_logs`, `/upload`. Браузер видит один origin → CORS/MJPEG-проблем нет, код фронта (`client.ts` `BASE=""`) не меняется.

### Миграции БД (Alembic)
```bash
alembic revision --autogenerate -m "описание"   # конфиг в migrations/alembic.ini, env в migrations/env.py
alembic upgrade head
```
`init_db()` в `backend/app.py` при старте делает `Base.metadata.create_all` — для свежей БД миграции не обязательны, нужны при изменении схемы существующей.

### Модели
- YOLO-веса в git: `models/best.pt` (PPE-детектор, 10 классов), `models/yolov8n-pose.pt` (жесты), `models/yolov8n.pt`.
- `models/buffalo_l/` (InsightFace, ~190 МБ) в `.gitignore`. Докачка: `python download_models.py` (идемпотентно). В Docker качается в рантайме из `entrypoint.sh` — НЕ на этапе build, т.к. `./models` монтируется volume'ом и перекрывает COPY из образа.
- Каталог моделей берётся из `INSIGHTFACE_ROOT` (в контейнере `/app`), иначе — корень репо; ожидается `<root>/models/buffalo_l/`.
- `_resolve_model()` в `backend/main.py`: если рядом с `.pt` лежит `.engine` (TensorRT FP16) — грузится он. При TensorRT имена классов берутся из движка, `CLASS_NAMES` НЕ применяется.

---

## 2. Архитектура

### 2.1. Корневые шим-модули — НЕ дубли
`app.py`, `config.py`, `main.py`, `state.py`, `camera.py`, `detection.py`, `gestures.py`, `reid.py`, `visualization.py` в корне репо — тонкие реэкспорты из `backend/` (`from backend.X import *`). Существуют ради совместимости импортов (`Procfile` → `app:app`, dev-маунты Docker). **Логику править в `backend/`, не в корневых шимах.** Точка входа: `app.py` → `backend.app:app`.

### 2.2. Поток обработки кадра
1. **Захват** — `backend/capture/camera.py::CameraCapture` (поток на камеру) читает источник → пишет последний кадр в `FrameBuffer` (`backend/capture/buffer.py`, потокобезопасный single-slot с `Event`-сигналом). Стратегия источника в `_loop()`:
   - RTSP: NVIDIA GStreamer (если есть `nvv4l2decoder`) → иначе ffmpeg-subprocess → иначе OpenCV(`CAP_FFMPEG`). Кадры 1280×720, `-r 15`, `-rtsp_transport tcp`, клиентский таймаут через `-stimeout` (НЕ `-timeout` — тот для listen-режима).
   - Локальная камера (int source): OpenCV → fallback ffmpeg v4l2.
   - Авто-переподключение с экспоненциальным backoff; чёрные кадры (`mean<3`) отбрасываются.
2. **Детекция** — `backend/main.py::_camera_detection_worker(cam_id)` — **daemon-поток НА КАЖДУЮ камеру** (параллельно, не round-robin). `start_live` поднимает по потоку на камеру + отдельный `_heartbeat_loop`. Каждый поток блокируется на `FrameBuffer.wait()`, читает кадр → `process_frame` → пишет в `annotated_buffers[cam_id]`. Параллелизм реален, т.к. YOLO/InsightFace/OpenCV отпускают GIL на вычислениях (на CPU — по ядрам, на GPU — с перекрытием Python-склейки; агрегатный FPS на одном GPU всё равно ограничен GPU).
   - **Модели на камеру** (`_cam_models`, `_get_cam_models`): свой экземпляр YOLO+pose на камеру — ByteTrack хранит трекер ВНУТРИ модели, общий объект перемешал бы `track_id`. Веса ~6 МБ, дёшево. Глобальные `model`/`pose_model` остаются только для `/upload`.
   - `process_frame(..., det_model=None, det_pose=None)` — модели прокидываются параметрами (по умолчанию глобальные → совместимость с `/upload` и тестами).
   - `add_camera`/`remove_camera`/`rename_camera` поднимают/снимают поток камеры на лету; воркер сам завершается по условию `cam_id in CAMERAS`.
3. **`process_frame`** (`main.py`, ядро бизнес-логики): `run_detection` → построение опасной зоны → сопоставление СИЗ с людьми → Re-ID → жесты/пропуск → отрисовка → возвращает `(frame, message, category, global_ids, statuses)`. `category` ∈ {`норма`, `внимание`, `нарушение`}.
4. **Раздача** — `backend/api/detection.py`: `/video_frame/<cam_id>` (одиночный JPEG, фронт поллит ~100мс, quality=85), `/video_feed[/<cam_id>]` (MJPEG `multipart/x-mixed-replace`).
   - **Детект потери камеры**: `FrameBuffer.age()` (время с последней записи capture). Если raw-буфер старше `STREAM_STALE_SEC`(6с) — воркер не гоняет YOLO по застывшему кадру (continue), а `/video_frame` отдаёт 204 → фронт показывает «NO SIGNAL» вместо замороженного «живого» кадра. capture при этом сам переподключается с backoff.

> ⚠️ Состояние `DetectionState` хитят параллельно N потоков детекции + N face-воркеров — все мутации под локами (`_lock`/`_reid_lock`). `get_global_id` под `_reid_lock` сериализует Re-ID между камерами (нужно для консистентности кросс-камерной личности; быстро относительно YOLO).

### 2.3. Детекция (`backend/detection/engine.py`)
- `run_detection(frame, model)` → `model.track(..., persist=True, tracker=bytetrack_custom.yaml)`, возвращает dict: `persons`, `person_track_ids`, `helmets`, `masks`, `vests`, `cones`. Классы фильтруются по русским именам из `CLASS_NAMES`.
- `bytetrack_custom.yaml`: `track_buffer: 90`, пороги 0.25/0.1 — для устойчивых `track_id` между кадрами.
- `get_danger_zone(cones)` — bbox по ≥`MIN_CONES`(2) конусам + расширение `ZONE_EXPAND_PX`(20). `is_in_danger_zone` проверяет точку ног (центр низа bbox). `has_item_on_person` — СИЗ засчитывается, если центр предмета в верхних `TOP_RATIO`(0.4) человека.
- **Пользовательские зоны** (`backend/zones.py`) — нарисованные оператором полигоны (редактор зон), в дополнение к авто-зоне по конусам. Хранятся в конфиге камеры (`cameras_config.json`, ключ `zones`), координаты **нормализованные [0..1]**. Типы: `danger`/`restricted` (вход = опасная зона, учитываются вместе с конусной в `_in_danger` внутри `process_frame`), `mask` (объекты в области исключаются из детекции — `apply_masks` до всей логики). Проверка вхождения — тот же ray-casting (`_point_in_polygon`), без shapely. CRUD: `get_zones`/`set_zones`/`add_zone`/`update_zone`/`delete_zone`. Hot-reload: читаются в `process_frame` на каждом кадре.
- **Пер-зонные требования СИЗ** (`zones.required_ppe`): какие СИЗ обязательны для человека = объединение `require_ppe` danger/restricted-зон, в которых он стоит (пусто → СИЗ не нужны); вне зон и в зоне по конусам — глобальный дефолт `PPE_REQUIRED_DEFAULT` (`config.py`, env). Это управляет `missing`/`fully_equipped`/нарушением и компактным статусом (необязательный СИЗ не считается отсутствующим). Демо/выставка: `PPE_REQUIRED_DEFAULT=mask` (только маска) или `PPE_REQUIRED_DEFAULT=` (СИЗ не нужны нигде), либо нарисовать зону с нужным `require_ppe`.

### 2.4. Состояние (`backend/core/state.py::DetectionState`)
Потокобезопасный (два лока: `_lock` общий, `_reid_lock` для Re-ID) синглтон, держит:
- **Логи** — кольцевой буфер `MAX_LOG_SIZE`(100) `LogEntry` (`backend/core/models.py`).
- **Пропуска** (`_approved`) — `global_id → expiry`, TTL `APPROVAL_DURATION`(300с). Выдаются по жесту ОК при полном комплекте СИЗ.
- **Маппинг трек→личность** (`_track_to_global`), `get_global_id()` — связывает ByteTrack `track_id` с устойчивым `global_id` из галереи. Логика «липкости» и троттлинга — см. 2.5.
- **Дедуп логов** — `is_status_changed()` логирует только при смене компактного статуса СИЗ (`КМЖЗ`), чтобы не спамить.
- **UI-уведомления** — `push_notification(type,title,sub)`/`pop_notifications()` — структурированная очередь (жест ОК «granted» / нехватка СИЗ «missing»), пушится в `process_frame` в момент жеста. Фронт поллит `/api/notifications` (`useServerNotifications`) и показывает сверху. НЕ парсится из текста логов (точнее, не зависит от дедупа). На стрим текст «ОДЕНЬТЕ СИЗ» больше не рисуется.
- **Голосовые предупреждения** — `push_voice_alert(cam_id,text)`/`pop_voice_alert()` — потокобезопасная очередь (deque max 50) с кулдауном `VOICE_ALERT_COOLDOWN`(15с) на камеру. Текст формирует `_build_voice_text` (чистая функция в `backend/tts/alert.py`, реэкспорт в `main.py`; имя нарушителя по Re-ID + перечень отсутствующих СИЗ — **только при нарушении внутри опасной зоны**, иначе `""`). Пушится из `detection_loop` на каждом кадре зонного нарушения **независимо от записи клипа** (троттлинг кулдауном; раньше пушился только при старте записи — вход в зону мог не озвучиться). Фронт поллит `/api/voice_alert` (`useVoiceAlerts`). **Синтез — на бэкенде через Piper** (`backend/tts/`, см. ниже); фронт получает готовый WAV с `/api/voice_alert_audio?text=...` и играет через `<audio>`. **Fallback:** если бэкенд-TTS вернул 503 (нет piper/модели/`TTS_ENABLED=false`) — озвучка через Web Speech API браузера (зависит от русского TTS-голоса ОС, см. раздел 4).

### 2.4.1. Бэкенд-синтез речи (`backend/tts/`, Piper TTS)
Речь для тревог синтезируется **на сервере** фиксированным русским голосом Piper и отдаётся фронту готовым WAV — качество не зависит от TTS-голосов ОС оператора (корневая причина «быстро и неразборчиво», см. раздел 4).
- **`PiperTTSService`** (`service.py`, синглтон `get_tts_service()`) — ленивая загрузка голоса (ONNX), потокобезопасный, **синтез по запросу на эндпоинте** (НЕ при `push_voice_alert` — горячий путь `detection_loop` не трогаем, аудио-байты в `DetectionState` не храним). LRU-кэш по нормализованному тексту (`TTS_CACHE_SIZE`=64) — повторные одинаковые алерты не пересинтезируются.
- **`normalize_for_tts`** (`text.py`, чистая/тестируемая) — «красивая речь»: раскрывает «СИЗ» → «средств защиты», убирает `_`/`#` из имён Re-ID, схлопывает пробелы, добавляет завершающую пунктуацию.
- **`ensure_model`** (`models.py`) — идемпотентно качает голос (`TTS_MODEL`=`ru_RU-irina-medium`) из HuggingFace в `TTS_MODEL_DIR` (`models/piper/`, в `.gitignore`). Прогревается в фоне при старте (`app.py`).
- **Эндпоинт** `GET /api/voice_alert_audio?text=...` (`router.py`, `tts_bp`) → `audio/wav` (200) либо 503 (фронт откатывается на Web Speech).
- **Мягкая деградация:** весь импорт `piper` ленивый. Нет `piper-tts`/модели/`TTS_ENABLED=false` → 503, система работает на Web Speech. Тесты (`tests/test_tts.py`) piper НЕ требуют.
- **Зависимость `piper-tts`** — в `requirements.txt` и `Dockerfile`/`Dockerfile.gpu` (не в Jetson/frontend-образах: там бэкенд не исполняется, `piper-phonemize` на ARM проблемен). На работающем прод-контейнере ставится вручную по ssh: `pip install piper-tts==1.2.0` + restart.
- `cleanup_stale_tracks()` чистит треки старше `TRACK_EXPIRY`(60с); `clear_tracks()` — при `start_live`.

### 2.5. Re-ID лиц (`backend/reid/`) — самая хрупкая часть
- `FaceRecognizer` (`recognizer.py`) — InsightFace `buffalo_l`, провайдеры CUDA→CPU, 3 попытки загрузки (чистит пустую папку модели и докачивает). `detect_faces` возвращает `(bbox, нормализованный эмбеддинг 512d, quality)`. `quality` = `det_score*0.7 + size_score*0.3`, клампится в [0.35, 1.0].
- `FaceRecognitionWorker` — отдельный поток **на камеру**, детектит лица каждый `REID_FRAME_SKIP`(3) кадр, кеширует `_latest_faces`. Стартует/останавливается по флагу `DETECT_MODES["faces"]` (`start_face_workers`/`stop_face_workers` в `main.py`).
- `match_faces_to_persons` — сопоставляет лица людям по overlap/центру bbox.
- `FaceGallery` (`gallery.py`) — pickle-хранилище `data/face_gallery.pkl`. Ключевое:
  - **Адаптивный порог** `_adaptive_threshold(quality)`: 0.45 (отл) … 0.60 (плох). Чем лучше лицо — тем строже не нужно. Дополнительно порог снижается для записей с ≥2 и ≥5 эмбеддингами.
  - **Защита якоря** `_append_embedding`: при переполнении (`max_embeddings`=`REID_MAX_EMBEDDINGS`=30) выбрасывается индекс 1, а не 0 — первый (эталонный) эмбеддинг неприкосновенен. «Запоминание со всех сторон»: до 30 ракурсов на личность.
  - **Diversity-гейт** (`diverse=True` в «липком» пути `add_observation`): новый эмбеддинг добавляется, только если max косинус к уже сохранённым < `REID_DIVERSITY_MAX_SIM`(0.92) — копим разные ракурсы, а не почти-дубли одного кадра.
  - `match_or_register` / `add_observation` / `merge_entries` (auto-merge дубликатов) / `cleanup_old`: при `REID_MAX_AGE_DAYS`=0 авто-удаление **отключено** (личности хранятся «навсегда»).
- **`get_global_id`** в `state.py` — сердце стабильности имён (исторический баг «всё слетало на Гость_N»):
  - **Троттлинг хранения**: эмбеддинг добавляется в галерею не чаще `REID_STORE_INTERVAL`(1.5с) с одного трека и только при `quality ≥ REID_MIN_STORE_QUALITY`(0.55). Иначе кэш детектора вытеснял эталоны.
  - **«Липкость»**: если у трека уже есть личность и новое лицо её подтверждает по мягкому порогу (`threshold_for(q) - REID_STICKY_MARGIN`(0.25), но не ниже `REID_STICKY_MIN`(0.28)) — не пересматчиваем. Усиленный margin удерживает личность даже на слабо похожем ракурсе одного человека (sim 0.3-0.5), а разные люди (~0) переключаются. Лечит «постоянную перезапись» имён на стриме.
  - Перенос fallback-имён и merge при смене global_id.
- **Body Re-ID — опознание «со спины»** (`backend/reid/body.py::BodyRecognizer` + поля `body_embeddings` в галерее + ветки в `get_global_id`). Цветовой дескриптор одежды (HSV-гистограммы торса/ног, L2-норма, косинус ∈ [0,1]) — одинаков с лица и со спины, без тяжёлых зависимостей. Пока лицо видно, тело личности **запоминается** (`_store_body`, троттлинг `REID_BODY_STORE_INTERVAL`, diversity-гейт); когда лица нет и трек новый — личность **восстанавливается** через `FaceGallery.match_body` (порог `REID_BODY_MATCH_THRESHOLD`=0.82). Консервативно: только восстанавливает (не перекрывает лицо) и не присваивает личность, активную на другом треке (`_gid_active_on_other_track`). Дескриптор берётся с **чистого кадра** (`clean_frame` в `process_frame`, до отрисовки — иначе заливка зоны исказит цвета). Конфиг — `REID_BODY_*`; управляется тем же тумблером Re-ID («faces»). `BodyRecognizer.extract()` изолирован — цветовой бэкенд заменяем на OSNet/torchreid.
- `worker.py::FaceDetector` (YOLO `yolov8n-face.pt`) — **по сути не задействован** в основном пайплайне (лица детектит InsightFace). Файла `models/yolov8n-face.pt` в репо нет — `FaceDetector` тихо не загрузится. Не опираться на него.

### 2.6. Жесты (`backend/gestures/detector.py`)
- `detect_ok_gesture` — YOLOv8-pose находит поднятую руку (запястье выше плеча) → кроп кисти → OpenCV-контурный анализ (`convexityDefects`) считает «дырки» жеста ОК (`DEFECT_MIN..MAX`). Это эвристика на классическом CV, не ML-классификатор.
- `detect_raised_hand` — запястье выше носа. Кулдаун жестов `GESTURE_COOLDOWN`(3с) на личность (`can_gesture`).
- **Троттлинг pose-инференса**: `detect_ok_gesture` дорогой (отдельный YOLO-pose проход на кроп человека), поэтому в `process_frame` запускается только если `not approved and can_gesture(gid) and should_run_gesture(gid)` — последний ограничивает запуск до раза в `GESTURE_CHECK_INTERVAL`(0.5с) на личность. Без этого толпа из N человек = N pose-инференсов на каждый кадр → просадка FPS.

### 2.7. События и хранение
- В `detection_loop` при `category == "нарушение"` стартует запись клипа: pre-буфер `_frame_prebuf` (`EVENT_PRE_FRAMES`=30) + кадры нарушения + post-кадры (`EVENT_POST_FRAMES`=30 после спада), максимум `EVENT_MAX_FRAMES`=300.
- `_finalize_recording`: cv2 пишет raw mp4 → **ffmpeg перекодирует в H.264** (`libx264 ultrafast yuv420p`) → загрузка в storage + снапшот из середины клипа.
- `backend/storage/minio_client.py::EventStorage` — S3-клиент (boto3) к MinIO (bucket `events`, ключи `clips/<cam>/<id>.mp4`, `snapshots/...`). **Локальный fallback** в `violation_logs/<cam>/`: при недоступности MinIO ИЛИ при сбое загрузки в середине сессии клип не теряется, пишется на диск; чтение пробует MinIO, затем локально. Синглтон через `get_storage()`.
- Метаданные событий → SQLite (`backend/api/events.py::create_event_record`).

#### 2.7.1. NVR — непрерывная запись архива (`backend/recorder.py`)
Отдельно от event-клипов (только нарушения) — **непрерывный архив** для отмотки на любой момент. По умолчанию ВЫКЛЮЧЕНО (`RECORD_ENABLED`).
- **`SegmentRecorder`** (на камеру): ffmpeg режет RTSP на сегменты `RECORD_SEGMENT_SEC`(60с) через `-c copy` (перепаковка без перекодирования → ~0% CPU). Открывает RTSP **второй раз** (помимо `CameraCapture`) — нужно, т.к. capture декодирует в raw. Файлы: `<RECORD_DIR>/<cam>/recordings/ГГГГ/ММ/ДД/ЧЧ.ММ.СС.mp4` (локальный диск, не MinIO — терабайты архива дешевле локально). Только для строковых (RTSP/файл) источников, не для `int`-камер.
- **Индекс** в таблице `Recording` (`index_segment_file`): `index_new_segments` сканирует завершённые `.mp4` (mtime старше 5с = ffmpeg дописал) и пишет ряд (start из имени, end=mtime, size, has_motion). Идемпотентно по `path`.
- **`RetentionCleaner`/`plan_deletions`** (чистая логика, тестируема): удаляет (1) старше `RECORD_RETAIN_DAYS`(7); (2) в `RECORD_MODE="motion"` — сегменты без движения старше `RECORD_MOTION_GRACE_SEC`(120с), **но только для камер, у которых есть хоть один motion-сегмент** (защита от потери данных, если motion-пайплайн выключен); (3) при занятости диска выше `RECORD_MAX_DISK_PERCENT`(80%) — старейшие.
- **`RecordingManager`** (синглтон `get_recording_manager()`): поднимает/останавливает рекордеры вместе с `start_live`/`stop_live`, фоновым циклом индексирует и чистит, принимает `note_motion(cam_id)` из потока детекции (флаг `has_motion` сегмента). В режиме "motion" поток детекции считает MOG2 даже если «Motion First» (`MOTION_DETECTION_ENABLED`) выключен.
- API — см. 2.9 (`api/recordings.py`).
- Таблица `Recording` создаётся `init_db()` (`create_all`) для свежей БД; для существующих прод-БД есть Alembic-миграция `a1b2c3d4e5f6_add_recordings` (`alembic upgrade head`).

### 2.8. БД (`backend/db/`)
- SQLAlchemy + SQLite `data/ppe.db`, `check_same_thread=False`, `scoped_session`. `get_session()` на каждый запрос, закрывать вручную.
- Модели (`db/models.py`): `User` (роли admin/operator/viewer/api), `ApiKey`, `Camera`, `Event`, `Recording` (сегменты NVR-архива). Enum'ы `EventLabel`, `SubLabel`, `UserRole`.
- ⚠️ **Рантайм-источник камер — JSON, не БД.** Источник истины для рантайма — `data/cameras.json` (+ `data/cameras_config.json`). Таблица `Camera` теперь **синхронизируется** функциями `main.py` (`_db_upsert_camera`/`_db_delete_camera` вызываются из `add_camera`/`remove_camera`/`rename_camera`) — для целостности FK `Event.camera_id`/`Recording`. Но при ручной правке JSON в обход функций возможен рассинхрон; SQLite FK по умолчанию не enforced.

### 2.9. API (Flask blueprints, регистрируются в `backend/app.py`)
- **`api/detection.py`** (`configure_detection_routes`): `POST /start`, `POST /stop`, `/video_frame/<cam>`, `/video_feed[/<cam>]`, `GET|PUT /api/detect-modes`, `GET /api/status`, `GET /api/voice_alert`, `GET /api/notifications` (очередь UI-уведомлений), `/detection_log`, `/export_logs` (CSV с BOM), `POST /upload` (детекция на загруженном фото/видео).
- **`api/cameras.py`**: `GET /cameras`, `POST /api/cameras`, `PUT|DELETE /api/cameras/<id>`, `POST /api/cameras/<id>/rename`, `PUT /api/cameras/<id>/analytics` (вкл/выкл детекцию на камере), `GET|PUT|POST /api/cameras/<id>/zones` + `PUT|DELETE /api/cameras/<id>/zones/<zone_id>` (зоны редактора). CRUD камер идёт через функции `main.py` (`add_camera`/`remove_camera`/`rename_camera`) — они синхронно правят буферы, воркеры, `cameras.json` и таблицу `Camera`. `POST /api/cameras/discover` (`{add:bool}`) — автообнаружение RTSP в локальной сети (см. ниже).
- **`api/reid.py`**: `GET /api/reid/persons`, `POST .../rename`, `DELETE .../<id>`, `POST /api/reid/clear`, `GET /api/reid/stats` — управление галереей лиц.
- **`api/events.py`** (Blueprint `events_bp`): `GET /api/events` (фильтры camera/label, пагинация), `GET /api/events/<id>`, `.../clip`, `.../snapshot`.
- **`api/monitoring.py`** (Blueprint `monitoring_bp`): `GET /health` (healthcheck), `GET /metrics` (Prometheus text), `GET /api/stats` (JSON-метрики). Читают реестр `backend/core/metrics.py`.
- **`api/recordings.py`** (Blueprint `recordings_bp`): `GET /api/recordings` (фильтры cam_id/from/to, пагинация), `GET /api/recordings/at?cam_id=&ts=` (сегмент по моменту времени), `GET /api/recordings/<id>`, `GET /api/recordings/<id>/play` (отдача mp4 с Range/перемоткой). Источник — таблица `Recording` (NVR, см. 2.7.1).
- **`auth/routes.py`** (`/api/auth`): `register`, `login`, `refresh`, `me`, `POST /api-keys` (admin).
- CORS открыт (`*`) на все ответы (`add_cors` в `app.py`).

### 2.10. Авторизация (`backend/auth/`)
- JWT (`PyJWT`, HS256). Access 15 мин, refresh 7 дней. Секрет: env `JWT_SECRET` → иначе `data/jwt_secret.txt` → иначе генерируется и сохраняется.
- `service.py`: `login_user`/`refresh_token`/`register_user`/`create_api_key`/`verify_api_key`. Пароли — `werkzeug.security`.
- `middleware.py`: декораторы `@login_required` (Bearer JWT или API-ключ), `@admin_required`, `@api_key_required`. Кладут юзера в `flask.g`.
- ⚠️ Большинство детекшен/камера-роутов **не защищены** декораторами — авторизация в основном на фронте. Не считать API закрытым.

### 2.11. Режимы детекции
`DETECT_MODES = {people, ppe, faces}` (`backend/config.py`), персистятся в `data/detect_modes.json`, меняются через `PUT /api/detect-modes` / UI. Если все три выключены — YOLO пропускается целиком. Выключение `people` каскадно гасит `ppe` и `faces`. Переключение `faces` стартует/глушит face-воркеры на лету.

### 2.12. Фронтенд (`frontend/`)
- React 19 + TypeScript + Vite 6, роутинг `react-router-dom` v7 (`App.tsx`: Dashboard, EventsPage, ArchivePage `/archive`, ZonesPage `/zones`, SettingsPage, Login/Register).
- **`ZonesPage`** (`/zones`) — редактор зон: SVG (`viewBox 0 0 1 1`, нормализованные координаты) поверх кадра камеры (`/video_frame`); клик = добавить вершину активной зоне, перетаскивание вершин (pointer events), выбор типа/названия/требуемых СИЗ; сохранение через `api.saveZones` (PUT всех зон).
- **`ArchivePage`** (`/archive`) — просмотр NVR-архива: выбор камеры+даты → `api.getRecordings({camId, from, to})` + `api.getEvents` → 24-часовой таймлайн сегментов (цвет = есть движение) с **метками событий** поверх (цвет по label); клик по метке → открывает покрывающий сегмент и перематывает к моменту события (`onLoadedMetadata` → `currentTime`), при отсутствии сегмента — fallback на event-клип. Плеер с перемоткой (Range через `/api/recordings/<id>/play`) и **непрерывным воспроизведением** (тумблер «Непрерывно»: по `onEnded` автозапуск следующего сегмента, пропуская gaps motion-режима). Появляется при `RECORD_ENABLED` на бэке.
- **Логи — единый источник**: поллинг `/detection_log` живёт в `CameraContext` (один интервал 1.5с при `isRunning`), `logs` отдаётся через контекст; Dashboard и DispatcherPanel читают их оттуда (фильтруют по камере локально), не плодя параллельных интервалов.
- `src/api/client.ts` — HTTP-клиент с авто-refresh JWT. `src/contexts/` — Auth, Camera. `src/hooks/` — useBreakpoint, useOrientation, useClock, useCameras, useLogs, **useVoiceAlerts** (поллит `/api/voice_alert`, озвучивает через Web Speech API; голоса кэшируются по `voiceschanged` — иначе `getVoices()` пуст на первом вызове и кириллицу читает англ. голос), **useServerNotifications** (поллит `/api/notifications`, шлёт в верхнюю панель `Notifications`).
- Адаптив 3 брейкпоинта (моб <768 / планшет 768–1199 / десктоп ≥1200): дизайн-токены `src/design/tokens.ts`, UI-примитивы `src/components/ui/` (Box, Flex, Grid, Responsive, BottomSheet).
- Дев-сервер проксирует список префиксов API на удалённый бэк (`vite.config.ts`, env `VITE_API_TARGET`).

### 2.13. Motion detection / MQTT / Observability (Frigate-слой)
Три опциональных подсистемы, по умолчанию **выключены** (не меняют поведение), включаются конфигом/env. Интегрированы в `detection_loop`.
- **Motion detection** (`backend/detection/motion.py::MotionDetector`) — вычитание фона MOG2 + морфология + контуры, по экземпляру на камеру (`_motion_detectors` в `main.py`, сбрасываются на `start_live`). При `MOTION_DETECTION_ENABLED` (env-тумблер) кадры без движения **не прогоняются через YOLO** (экономия CPU): в `out_buf` пишется raw-кадр, считается `record_skipped`. Не пропускает кадры во время активной записи события (нужен пост-буфер). Антидребезг — `MOTION_COOLDOWN_FRAMES` кадров удержания после спада. Параметры: `MOTION_THRESHOLD`/`MOTION_MIN_AREA`/`MOTION_COOLDOWN_FRAMES`.
- **MQTT** (`backend/mqtt/publisher.py::MqttPublisher`, синглтон `get_publisher()`) — публикация в брокер (eclipse-mosquitto уже в `docker-compose.yml`). Топики `${MQTT_TOPIC_PREFIX=frigate}/<cam>/{motion,detection,violation,approved}` + `frigate/system/{heartbeat,status}`. **Опционален и мягко деградирует**: нет `paho-mqtt` / `MQTT_ENABLED=false` / брокер недоступен → no-op, пайплайн не падает (connect_async + loop_start, Last-Will `offline`). `MQTT_HA_DISCOVERY` публикует конфиги Home Assistant MQTT discovery (motion/people/violations сенсоры). Все настройки — env (`MQTT_ENABLED`/`MQTT_HOST`/`MQTT_PORT`/`MQTT_USER`/`MQTT_PASSWORD`/`MQTT_TOPIC_PREFIX`/`MQTT_HA_DISCOVERY`).
- **Автообнаружение камер** (`backend/discovery.py`) — поиск непаролёных RTSP в локальной сети: ONVIF WS-Discovery (multicast UDP 3702, raw-сокет без зависимостей) + фоллбэк-скан подсети (порт 554 + типовые RTSP-пути). «Непаролёность» = поток реально открывается без логина (`probe_rtsp` через OpenCV). `discover_cameras(add)`/`autodiscover_and_add` в `main.py`; API `POST /api/cameras/discover`; кнопка «Найти камеры» в `CameraManagerModal`. Автозапуск при старте — флаг `CAMERA_AUTODISCOVER` (фон, по умолчанию off). ⚠️ В Docker ONVIF-multicast требует `network_mode: host`. Чистые помощники (`ips_from_ws_responses`/`candidate_urls`/`subnet_hosts`) тестируются без сети.
- **RTSP-рестрим вебки** (`mediamtx.yml` + сервис `mediamtx` в `docker-compose.frontend.yml`, профиль `webcam`) — когда фронт и бэк на разных серверах, а USB-вебка у фронта: MediaMTX на фронт-сервере захватывает `/dev/video0` (ffmpeg, ultrafast+zerolatency) и публикует `rtsp://<FRONTEND_HOST>:8554/webcam`; бэк добавляет эту камеру как обычный RTSP. Без рефакторинга приложения (бэку приходит обычный RTSP-URL).
- **Метрики** (`backend/core/metrics.py::MetricsRegistry`, синглтон `get_metrics()`) — потокобезопасный реестр: FPS (скользящее окно 5с) и латентность детекции по камерам, счётчики обработанных/пропущенных кадров, события по `category`, аптайм, системные (psutil). Эндпоинты — см. 2.9 (`/health`, `/metrics`, `/api/stats`). `detection_loop` пишет `record_frame`/`record_skipped`/`record_event` и шлёт MQTT-heartbeat раз в `MQTT_HEARTBEAT_INTERVAL`.

---

## 3. Конфигурация
- Основные константы — `backend/config.py` (пороги, тайминги, цвета, `CLASS_NAMES`, Re-ID/Event/MinIO-параметры). `CLASS_NAMES` переопределяет имена классов модели **только для `.pt`** (не для `.engine`).
- Рантайм-состояние в `data/`: `cameras.json`, `cameras_config.json`, `detect_modes.json`, `face_gallery.pkl`, `ppe.db`, `jwt_secret.txt`.
- Env: `JWT_SECRET`, `ADMIN_USERNAME`/`ADMIN_PASSWORD`/`ADMIN_EMAIL`, `INSIGHTFACE_ROOT`, `VITE_API_TARGET` (фронт), `BACKEND_URL` (nginx-фронт). Frigate-слой (2.13): `MOTION_DETECTION_ENABLED`, `MQTT_ENABLED`/`MQTT_HOST`/`MQTT_PORT`/`MQTT_USER`/`MQTT_PASSWORD`/`MQTT_TOPIC_PREFIX`/`MQTT_HA_DISCOVERY`. NVR (2.7.1): `RECORD_ENABLED`, `RECORD_MODE`(motion/continuous), `RECORD_DIR`, `RECORD_SEGMENT_SEC`, `RECORD_RETAIN_DAYS`, `RECORD_MAX_DISK_PERCENT`, `RECORD_MOTION_GRACE_SEC`, `RECORD_CLEAN_INTERVAL_SEC`. Зоны: `PPE_REQUIRED_DEFAULT` (список через запятую: helmet,mask,vest; дефолт обязательных СИЗ вне зон). Автообнаружение: `CAMERA_AUTODISCOVER`, `DISCOVERY_USE_ONVIF`, `DISCOVERY_USE_SCAN`, `DISCOVERY_ONVIF_TIMEOUT`.

---

## 4. Известные ловушки
- **Слабые security-дефолты:** `admin/admin123`, MinIO `minioadmin/minioadmin` (в `config.py` и compose), пустой `JWT_SECRET` → автогенерация. Переопределять через env. Бизнес-API в основном не закрыты авторизацией.
- **Фейковые метрики во фронте:** часть статусов парсится из текста лог-строк; метрики CPU/RAM/FPS во фронте местами не настоящие. **Настоящие** метрики — в `/api/stats`, `/metrics` (см. 2.13), фронт их пока не потребляет.
- **Tesla P4 (Pascal, sm_61)** несовместима с torch cu124/cu130 → нужен torch 2.4.1 cu121 (см. `Dockerfile.gpu`, `DEPLOY_FRONTEND_CHECKLIST.md`). `requirements.txt` фиксирует torch 2.12.0 — это для CPU/современных GPU.
- **`FaceDetector`/`yolov8n-face.pt` — не задействованы** (см. 2.5).
- **Поток детекции на камеру** (см. 2.2): на одном GPU агрегатный FPS всё равно ограничен GPU (потоки перекрывают Python-склейку, но инференс на GPU сериализуется). Реальный рост FPS — на многоядерном CPU и при motion-гейте. N экземпляров YOLO в памяти (по 2 на камеру) — это норма, не утечка.
- **Камеры не в БД, а в JSON** (см. 2.8). Таблица `Camera` рассинхронизирована с рантаймом.
- **`stop_live` / `CameraCapture.stop`** — порядок важен: сначала рвём источник (terminate ffmpeg / release), потом join, иначе `/stop` висит на полном таймауте (по 5с/камеру). Исторический баг зависания.
- **RTSP ffmpeg:** клиентский таймаут — `-stimeout` (мкс), НЕ `-timeout` (тот трактуется как listen-режим → ошибка).
- **`cv2.INTER_NEAREST_EXACT`** шиммится в `app.py`/`main.py` для совместимости версий OpenCV.
- **Голосовые предупреждения: основной путь — бэкенд Piper TTS** (`backend/tts/`, см. 2.4.1), не зависит от ОС оператора. **Web Speech API — только fallback**, когда бэкенд-TTS недоступен (нет `piper-tts`/модели или `TTS_ENABLED=false` → 503). Web Speech требует русского TTS-голоса в ОС: `getVoices()` в Chrome пуст на первом вызове (голоса грузятся асинхронно) — `useVoiceAlerts` кэширует их по `voiceschanged`; без русского голоса кириллицу читает англ. голос «быстро и неразборчиво» → озвучка пропускается с предупреждением в консоли. Полное решение «неразборчивости» — поставить `piper-tts` на бэк (см. 2.4.1); запасное — русский голос в ОС (Windows: Microsoft Irina; Linux: RHVoice).
