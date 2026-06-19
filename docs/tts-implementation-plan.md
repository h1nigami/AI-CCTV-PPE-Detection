# План: Бэкенд TTS для голосовых предупреждений (Piper)

## Проблема

**Коммит 147633b** починил выбор русского голоса в Web Speech API, но он всё равно зависит от TTS-голосов ОС оператора. Без установленного русского голоса браузер читает кириллицу английским голосом — «быстро и неразборчиво».

**Текущий поток:**
Бэкенд (текст) → `/api/voice_alert` → Фронт (Web Speech API) → **OS-зависимое качество**

## Решение: Бэкенд TTS с Piper

Генерировать аудио на сервере, отдавать готовый WAV/MP3 фронту. **Piper TTS** — идеальный кандидат:
- **Быстрый** (real-time factor < 1 на CPU, ~50ms на синтез)
- **Лёгкий** (~50MB модель, зависимости: `onnxruntime` + `piper-phonemize`)
- **ONNX Runtime** — уже есть в стеке (insightface)
- **Поддерживает русский** (голос `ru_RU-irina-medium`)
- **Работает офлайн**, GPU не обязателен

---

## Изменения

### 1. Зависимости

```bash
pip install piper-tts
```

Добавить в `requirements.txt` и все Dockerfile'ы (`Dockerfile`, `Dockerfile.gpu`, `Dockerfile.jetson`).

### 2. Новый модуль `backend/tts/`

```
backend/tts/
├── __init__.py
├── service.py           # PiperTTSService (синглтон, ленивая загрузка)
├── models.py            # Скачивание/кэширование голосовых моделей
└── router.py            # Новый эндпоинт GET /api/voice_alert_audio/<id>
```

**`PiperTTSService`**:
- Синглтон с ленивой инициализацией (модель грузится при первом вызове)
- Модель скачивается в `models/piper/ru_RU-irina-medium.onnx` при первом запуске
- Потокобезопасный: синтез быстрый, можно в thread pool
- Кэш готового аудио (ключ = хеш текста) — повторные алерты не пересинтезируются

### 3. Изменение потока voice alert

**Сейчас:** `state.push_voice_alert(cam_id, text)` → хранит текст → `/api/voice_alert` отдаёт текст

**Новый:** `state.push_voice_alert(cam_id, text)` → генерирует аудио (async, non-blocking) → хранит bytes + text → `/api/voice_alert` отдаёт `{id, text, cam_id, audio_url}`

### 4. API

| Эндпоинт | Было | Стало |
|----------|------|-------|
| `GET /api/voice_alert` | `{id, text, cam_id}` | `{id, text, cam_id, audio_url}` |
| `GET /api/voice_alert_audio/<id>` | — | `audio/wav` (бинарник) |

### 5. Фронт: `useVoiceAlerts.ts`

- Убрать полностью Web Speech API (speechSynthesis, voiceschanged, speak)
- Получить аудио по `audio_url` → `new Audio(url).play()`
- Проще, надёжнее, не зависит от OS

### 6. Конфигурация (в `backend/config.py`)

```python
TTS_ENABLED = True
TTS_MODEL = "ru_RU-irina-medium"
TTS_MODEL_DIR = "models/piper"
TTS_SAMPLE_RATE = 22050
TTS_CACHE_SIZE = 50  # кэш аудио (последние N уникальных текстов)
```

### 7. Docker / Деплой

- Модель скачивается в рантайме (как InsightFace с `download_models.py`)
- Монтировать `models/piper/` как volume для персистентности

---

## Анализ Piper vs альтернативы

| Критерий | **Piper** | Coqui XTTS v2 | Edge-TTS | Bark |
|----------|-----------|---------------|----------|------|
| Скорость | ~50ms | ~2-5s | ~500ms | ~10s |
| Размер модели | ~50MB | ~1.2GB | Внешний API | ~2GB |
| Зависимости | ONNX Runtime | torch + transformers | HTTP | torch |
| Русский | ✅ | ✅ | ✅ | ❌ |
| Офлайн | ✅ | ✅ | ❌ | ✅ |
| GPU не нужен | ✅ | ❌ | ✅ | ❌ |

**Piper — оптимальный выбор для real-time алертов.**

---

## Компромиссы и решения

1. **Размер модели**: ~50MB на один голос. Начинаем с `irina-medium`. При необходимости добавить другие.

2. **Латентность**: ~50ms на CPU. Для алертов (не live-стрим) это незаметно. Если нужно — кэш повторных текстов.

3. **Фоллбэк**: Если TTS не удался (нет модели, OOM), оставляем текст в ответе. Фронт может тихо пропустить или попробовать Web Speech API (по желанию).

4. **Стриминг vs файл**: Для коротких алертов (1-2 предложения) отдаём полный WAV. Для длинных — можно чанками (не нужно, алерты короткие).

---

## Принятые решения (отклонения от первоначального плана)

1. **Ленивый синтез на эндпоинте, без байтов в `DetectionState`.** `push_voice_alert`
   по-прежнему хранит только текст; аудио синтезируется по запросу на
   `/api/voice_alert_audio?text=...` с кэшем по нормализованному тексту внутри
   `PiperTTSService`. Горячий путь `detection_loop` не трогается, состояние не пухнет.
2. **Web Speech оставлен как fallback** (не удалён). Если бэкенд-TTS вернул 503
   (нет piper/модели/`TTS_ENABLED=false`) — фронт озвучивает через Web Speech.
3. **`/api/voice_alert` не меняется** (обратная совместимость). Фронт сам строит
   URL аудио из текста (`api.getVoiceAlertAudioUrl`).
4. **`Dockerfile.jetson`/`Dockerfile.frontend` НЕ трогаем** — Jetson это фронт-сервер
   (nginx), бэкенд там не исполняется; `piper-phonemize` на ARM проблемен.
5. **Красивая речь** — `backend/tts/text.py::normalize_for_tts`: раскрывает «СИЗ» →
   «средств защиты», убирает `_`/`#` из имён Re-ID, схлопывает пробелы, добавляет
   завершающую пунктуацию.

## Порядок реализации

- [x] Создать `backend/tts/` — `text.py` (нормализация), `models.py` (скачивание
      голоса), `service.py` (`PiperTTSService`, синглтон, ленивый, кэш), `router.py`
- [x] Зарегистрировать `tts_bp` в `backend/app.py` + фоновый прогрев модели при старте
- [x] Конфиг в `backend/config.py` (`TTS_ENABLED`/`TTS_MODEL`/`TTS_MODEL_DIR`/`TTS_CACHE_SIZE`)
- [x] Тесты `tests/test_tts.py` (нормализация, кэш/деградация, парсинг модели, эндпоинт)
- [x] Переписать `frontend/src/hooks/useVoiceAlerts.ts` — бэкенд-аудио + Web Speech fallback
- [x] `requirements.txt` + `Dockerfile`/`Dockerfile.gpu` (`piper-tts==1.2.0`), `.gitignore` (`models/piper/`)
- [x] Обновить `CLAUDE.md`
- [ ] **Вручную на бэк-сервере (Tesla):** `pip install piper-tts==1.2.0` в контейнере +
      скачать голос (или дать ему скачаться при первом старте) + restart
