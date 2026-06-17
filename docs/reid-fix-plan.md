# ReID Name Loss Fix Plan

## Проблема: "Иван" → "Гость_N"

Пользователь переименован, но при перезапуске / появлении в профиль / плохом освещении лицо не матчится → создаётся новый gallery entry "Гость_N" или fallback "Гость_N".

## 4 точки отказа в ReID pipeline

### 1. Adaptive threshold слишком высок для профильных лиц

`backend/reid/gallery.py:54-62`:
```
quality >= 0.8 → 0.50
quality >= 0.6 → 0.55
quality >= 0.4 → 0.62
else            → 0.70
```

Профильное лицо (quality ~0.35) требует similarity > 0.70 для матча. Если реальная similarity = 0.65 — создаётся дубликат "Гость_N".

**Fix**: Снизить пороги до `0.45 / 0.50 / 0.55 / 0.60`

### 2. Сравнение со средним эмбеддингом, не с каждым

`backend/reid/gallery.py:74`:
```python
mean_emb = np.mean(data['embeddings'], axis=0)  # среднее размывает
```

Если у "Иван" 5 эмбеддингов (4 хороших + 1 плохой), среднее может не дотянуть до порога. При сравнении с каждым отдельным — хотя бы один пройдёт.

**Fix**: Сравнивать с каждым эмбеддингом, брать макс similarity.

### 3. Fallback создаётся до появления лица

`backend/core/state.py:80,118-128`:
```python
if face_embedding is not None:
    ... match_or_register ...
else:
    if old_id is None:
        global_id = hash(key)  # новый fallback "Гость_N"
```

Первые кадры трека ещё не имеют лица (face worker запущен с `frame_skip=3`). Сразу создаётся fallback. Когда лицо появляется — track уже имеет fallback ID.

**Fix**: Задерживать создание fallback на N кадров / ждать face embedding.

### 4. match_faces_to_persons — BBox overlap может не совпасть

`backend/reid/recognizer.py:139-151`:
```python
if ix2 > ix1 and iy2 > iy1:  # overlap > 0
    # только если face bbox пересекается с person bbox
```

При смещении детекций лица и человека — нет пересечения → `face_emb=None` → fallback.

**Fix**: Добавить fallback по центру bbox, не только overlap.

### 5. Quality score занижен для маленьких лиц

`backend/reid/recognizer.py:78-80`:
```python
face_size = min(face_w/frame_w, face_h/frame_h)
size_score = min(1.0, face_size / 0.15)    # лицо <15% кадра → <1.0
quality = det_score * 0.6 + size_score * 0.4
```

**Fix**: Уменьшить вес size_score до 0.3, добавить minimum floor 0.35.

## Порядок реализации

| # | Fix | Файл | Описание |
|---|-----|------|----------|
| 1 | Снизить адаптивные пороги | `gallery.py` | `0.45/0.50/0.55/0.60` |
| 2 | Сравнение с каждым эмбеддингом | `gallery.py` | `max(cosine_sim(emb_i))` вместо `cosine_sim(mean(all))` |
| 3 | Отложенное создание fallback | `state.py` | ждать face_emb до N кадров |
| 4 | Fallback матчинг face→person | `recognizer.py` | center distance при отсутствии overlap |
| 5 | Tweaks качества | `recognizer.py` | size_weight 0.3, floor 0.35 |
