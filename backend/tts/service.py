"""Бэкенд-синтез русской речи для голосовых предупреждений (Piper TTS).

Зачем: Web Speech API в браузере зависит от наличия русского TTS-голоса в ОС
оператора; без него кириллица читается «быстро и неразборчиво» (CLAUDE.md
раздел 4). Здесь речь синтезируется на сервере фиксированным русским голосом
Piper и отдаётся фронту готовым WAV — качество не зависит от машины оператора.

Деградирует мягко: если piper не установлен / модель не скачалась — synthesize
возвращает None, эндпоинт отдаёт 503, фронт откатывается на Web Speech.

Синтез ленивый и по запросу (на эндпоинте), а НЕ при push_voice_alert — горячий
путь detection_loop не трогаем, аудио-байты в DetectionState не храним. Кэш по
нормализованному тексту: повторные одинаковые предупреждения не пересинтезируются.
"""
import io
import threading
import wave
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from backend.config import TTS_ENABLED, TTS_MODEL, TTS_MODEL_DIR, TTS_CACHE_SIZE
from backend.tts.text import normalize_for_tts


class PiperTTSService:
    def __init__(self, enabled: bool = TTS_ENABLED, model_name: str = TTS_MODEL,
                 model_dir=TTS_MODEL_DIR, cache_size: int = TTS_CACHE_SIZE):
        self._enabled = enabled
        self._model_name = model_name
        self._model_dir = Path(model_dir)
        self._cache_size = max(0, int(cache_size))
        self._lock = threading.Lock()
        self._loaded = False
        self._available = False
        self._voice = None
        self._cache: "OrderedDict[str, bytes]" = OrderedDict()

    # ── Ленивая, потокобезопасная загрузка модели ──────────────
    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            if not self._enabled:
                print("[tts] Отключён (TTS_ENABLED=false)")
                return
            try:
                from piper import PiperVoice
                from backend.tts.models import ensure_model
                paths = ensure_model(self._model_dir, self._model_name)
                if paths is None:
                    print("[tts] Модель недоступна — синтез отключён")
                    return
                onnx_path, config_path = paths
                self._voice = PiperVoice.load(str(onnx_path), str(config_path))
                self._available = True
                print(f"[tts] Голос '{self._model_name}' загружен")
            except Exception as e:
                print(f"[tts] Не удалось инициализировать Piper: {e}")
                self._voice = None
                self._available = False

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._available

    # ── Синтез WAV (с кэшем по нормализованному тексту) ────────
    def synthesize(self, text: str) -> Optional[bytes]:
        """Вернуть WAV-байты речи для текста или None (если TTS недоступен)."""
        if not text or not text.strip():
            return None
        norm = normalize_for_tts(text)
        if not norm:
            return None
        # Кэш — быстрый путь, без загрузки модели.
        with self._lock:
            cached = self._cache.get(norm)
            if cached is not None:
                self._cache.move_to_end(norm)
                return cached
        if not self.available:
            return None
        try:
            audio = self._render_wav(norm)
        except Exception as e:
            print(f"[tts] Ошибка синтеза: {e}")
            return None
        if not audio:
            return None
        with self._lock:
            self._cache[norm] = audio
            self._cache.move_to_end(norm)
            while self._cache_size and len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return audio

    def _render_wav(self, text: str) -> bytes:
        """Синтезировать текст в WAV-байты (piper-tts: пишет заголовок+кадры)."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            self._voice.synthesize(text, wav)
        return buf.getvalue()


_service: Optional[PiperTTSService] = None
_service_lock = threading.Lock()


def get_tts_service() -> PiperTTSService:
    """Синглтон сервиса синтеза речи."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = PiperTTSService()
    return _service
