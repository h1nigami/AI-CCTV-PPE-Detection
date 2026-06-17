# Known Issues & Fixes

## Detection mode toggle (people/ppe/faces) не работает

**Симптом**: Клик по чекбоксу в Header → галка моргает и возвращается обратно.

**Причина**: `start_face_workers()` / `stop_face_workers()` кидает исключение → API возвращает 500 → фронтенд делает `catch { setModes(modes) }` и откатывает UI.

**Фикс** (`backend/api/detection.py`):
```python
try:
    if new_faces and start_face_workers:
        start_face_workers()
    elif not new_faces and stop_face_workers:
        stop_face_workers()
except Exception as exc:
    print(f"[Detection] Face worker switch failed: {exc}")
```

**Доп. причина**: `save_detect_modes()` падает если нет `data/` директории.

**Фикс** (`backend/config.py`):
```python
def save_detect_modes():
    _DETECT_MODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ...
```

---

## Видеоклип не грузится в EventsPage

**Симптом**: Событие есть, `hasClip: true`, но браузер показывает чёрный экран / «Видео недоступно».

**Причина**: OpenCV (`cv2.VideoWriter`) пишет MPEG-4 Part 2 (`mp4v`). Браузеры не поддерживают этот кодек в MP4-контейнере — нужен H.264 (`avc1` / `libx264`).

**Фикс** (`backend/main.py` → `_finalize_recording`):
```python
# OpenCV пишет mp4v (черновик)
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(raw_path, fourcc, EVENT_CLIP_FPS, (w, h))
...
out.release()
# ffmpeg ремуксит в H.264
subprocess.run([
    "ffmpeg", "-y",
    "-i", raw_path,
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-pix_fmt", "yuv420p",
    final_path
], capture_output=True, timeout=60)
```

---

## Запись события обрывается без клипа (hasClip=false)

**Симптом**: Событие есть в БД, но `hasClip=false` → клип не отображается.

**Причина 1**: Детекция остановлена (`/stop`) во время активной записи — `_finalize_recording` не вызвана.

**Фикс** (`backend/main.py` → `stop_live`):
```python
for cam_id, rec in list(_event_recordings.items()):
    if rec.get('active'):
        rec['active'] = False
        _finalize_recording(cam_id, rec)
```

**Причина 2**: Исключение в `_finalize_recording` (MinIO недоступен, ffmpeg упал) — `update_event_clip` не вызывается.

**Фикс** (`backend/storage/minio_client.py`): `upload_clip`/`upload_snapshot` теперь при падении `put_object` (MinIO упал уже в процессе сессии, а не на старте) пишут в локальное хранилище вместо проброса исключения — клип не теряется, `update_event_clip` вызывается. Симметрично `get_clip_data`/`get_snapshot_data` при промахе MinIO читают локальную копию.
```python
if self._available:
    try:
        self._client.put_object(...)
        return ...
    except Exception as e:
        print(f"[Storage] ... не удалась ({e}), пишу локально")
# fallback на локальный диск
```

---

## /stop endpoint зависает

**Симптом**: POST /stop не возвращает ответ (таймаут).

**Причина**: `detection_loop` заблокирован на `raw_buf.read()` (RTSP поток не отдаёт кадр). `CameraCapture.stop()` не успевает разблокировать чтение до вызова `t.join(timeout=2)`.

**Фикс** (`backend/capture/camera.py` → `CameraCapture.stop`): источник рвётся ДО `join`. Поток захвата висит в блокирующем `read()` и не проверяет `_running`, поэтому сначала `_unblock_capture()` (terminate ffmpeg / `release()` cv2 — разблокирует `read`), затем `join`, затем `_unblock_capture()` повторно (цикл переподключения мог поднять новый процесс). Раньше `join(timeout=5)` выжидал полный таймаут на каждую камеру.
```python
def stop(self):
    self._running = False
    self._unblock_capture()      # разблокировать висящий read()
    if self._thread:
        self._thread.join(timeout=5)
    self._unblock_capture()      # добить переподключившийся процесс
    self.buffer.clear()
```
Доп. (`_open_opencv`): RTSP-фоллбэк через OpenCV открывается с `CAP_PROP_OPEN_TIMEOUT_MSEC`/`READ_TIMEOUT_MSEC = 5000`, чтобы зависший поток не блокировал `read()` бесконечно.

**Диагностика**: Если `/stop` всё ещё долго отвечает — проверить `docker logs ... | grep "Захват камеры остановлен"`; при экстремальном зависании источника остаётся `docker compose restart`.

---

## Re-ID: "Гость_X" вместо имени на профильном лице

**Симптом**: Человек с известным лицом отображается как "Гость_27".

**Причина 1**: Адаптивный порог слишком высокий для некачественного лица.

**Фикс** (`backend/reid/gallery.py`): Пороги снижены:
```python
# Было: 0.50/0.55/0.62/0.70 за качество отл/хор/ср/плох
# Стало: 0.45/0.50/0.55/0.60
```

**Причина 2**: Сравнение использовало среднее эмбеддинг (`mean(embeddings)`) — плохие кадры разбавляли хороший профильный.

**Фикс** (`backend/reid/gallery.py` → `match_or_register`):
```python
sim = max(cosine_sim(emb, e) for e in data['embeddings'])  # per-embedding
```

**Причина 3**: `match_faces_to_persons` использовал только IoU (bbox overlap) — при отсутствии overlap лицо не привязывалось к человеку.

**Фикс** (`backend/reid/recognizer.py` → `match_faces_to_persons`): Добавлена fallback по центроиду — если overlap нулевой, выбирается ближайший по центру лицо.

**Причина 4**: `size_score` в качестве эмбеддинга был завышен — маленькое лицо получало низкий quality → высокий порог.

**Фикс** (`backend/reid/recognizer.py` → `detect_faces`):
```python
# Было: size_score = min(1.0, face_size / 0.15), quality = det*0.6 + size*0.4, min=0.1
# Стало: size_score = min(1.0, face_size / 0.10), quality = det*0.7 + size*0.3, min=0.35
```

**Причина 5**: Трек переключился с fallback-имени на gallery entry — старый singleton entry не мёржится.

**Фикс** (`backend/core/state.py` → `get_global_id`):
```python
if old_gid and gallery.has_id(old_gid) and gallery.get_embedding_count(old_gid) <= 1:
    gallery.merge_entries(old_gid, gid)
```

**Причина 6**: `track_buffer` слишком мал — трек-id меняется при повороте человека.

**Фикс** (`backend/detection/bytetrack_custom.yaml`): `track_buffer: 90`

---

## MJPEG поток отваливается после навигации

**Симптом**: После перехода по страницам и возврата на Dashboard — video_frame показывает 404 или стоп-кадр.

**Причина**: Браузер кеширует MJPEG URL и переиспользует TCP-соединение, которое было закрыто.

**Фикс** (`frontend/src/components/CameraCard.tsx`):
```tsx
const mountTs = useRef(Date.now())
const src = `/video_frame/${cam.name}?m=${mountTs.current}`
```

---

## Upload: файл не скачивается (popup blocked)

**Симптом**: После загрузки изображения результат не скачивается (блокировка всплывающих окон).

**Причина**: `window.open()` блокируется браузером.

**Фикс**: `<a download>` клик вместо `window.open`.

---

## Upload: 500 Internal Server Error

**Симптом**: После загрузки изображения бэкенд возвращает 500.

**Причина**: `request.files["file"]` кидает KeyError если поле не `file`, или `send_file` не находит путь.

**Фикс** (`backend/api/detection.py`):
```python
file = request.files.get("file")
if file is None:
    return "No file uploaded", 400
```

**Доп. причина**: `UPLOAD_FOLDER` не абсолютный.

**Фикс**:
```python
UPLOAD_FOLDER = os.path.abspath("uploads")
```

---

## Conftest не может импортировать модули в тестах

**Симптом**: `pytest` падает с `ImportError: No module named 'numpy'`.

**Причина**: Dockerfile устанавливает пакеты через `pip install ... 2>&1 | tail -10` — если pip падает (например, таймаут PyTorch), `tail` маскирует exit code и сборка продолжается без части зависимостей.

**Фикс** (Dockerfile): Убрать `tail`, разделить pip install:
```dockerfile
RUN pip install ... --extra-index-url ... && \
    pip install boto3
```
