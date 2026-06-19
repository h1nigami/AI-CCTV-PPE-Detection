"""Тесты бэкенд-синтеза речи (Piper TTS).

Не требуют установленного piper: сервис мягко деградирует, а синтез в тестах
мокается. Покрытие: нормализация текста, кэш/деградация сервиса, парсинг имени
модели, эндпоинт /api/voice_alert_audio.
"""
import pytest
from flask import Flask

from backend.tts.text import normalize_for_tts
from backend.tts.service import PiperTTSService
from backend.tts.models import _voice_url_dir, ensure_model


# ── Нормализация текста ────────────────────────────────────
class TestNormalizeForTts:
    def test_empty(self):
        assert normalize_for_tts("") == ""
        assert normalize_for_tts(None) == ""

    def test_expands_siz_abbreviation(self):
        assert normalize_for_tts("Нет СИЗ: каска") == "Нет средств защиты: каска."

    def test_underscore_in_name(self):
        assert normalize_for_tts("Гость_3 в зоне") == "Гость 3 в зоне."

    def test_hash_in_name(self):
        assert "номер" in normalize_for_tts("#42 без каски")

    def test_collapses_whitespace(self):
        assert normalize_for_tts("Внимание!   человек\n в  зоне") == \
            "Внимание! человек в зоне."

    def test_adds_terminal_punctuation(self):
        assert normalize_for_tts("человек в зоне").endswith(".")

    def test_keeps_existing_punctuation(self):
        assert normalize_for_tts("Внимание!").endswith("!")
        assert not normalize_for_tts("Внимание!").endswith("!.")


# ── Сервис: кэш и деградация ───────────────────────────────
class TestPiperTTSService:
    def test_disabled_is_unavailable(self):
        svc = PiperTTSService(enabled=False)
        assert svc.available is False
        assert svc.synthesize("Привет") is None

    def test_empty_text_returns_none(self):
        svc = PiperTTSService(enabled=False)
        assert svc.synthesize("") is None
        assert svc.synthesize("   ") is None

    def test_synthesizes_and_caches(self, monkeypatch):
        svc = PiperTTSService(enabled=True)
        # Имитируем загруженную модель без реального piper.
        svc._loaded = True
        svc._available = True
        calls = []
        monkeypatch.setattr(svc, "_render_wav",
                            lambda text: calls.append(text) or b"RIFFfake")

        a1 = svc.synthesize("Нет СИЗ: каска")
        a2 = svc.synthesize("Нет СИЗ: каска")
        assert a1 == b"RIFFfake"
        assert a2 == b"RIFFfake"
        # Второй вызов — из кэша, рендер вызван один раз и с нормализованным текстом.
        assert calls == ["Нет средств защиты: каска."]

    def test_render_failure_returns_none(self, monkeypatch):
        svc = PiperTTSService(enabled=True)
        svc._loaded = True
        svc._available = True

        def boom(_text):
            raise RuntimeError("synth failed")

        monkeypatch.setattr(svc, "_render_wav", boom)
        assert svc.synthesize("Внимание") is None

    def test_cache_eviction(self, monkeypatch):
        svc = PiperTTSService(enabled=True, cache_size=2)
        svc._loaded = True
        svc._available = True
        monkeypatch.setattr(svc, "_render_wav", lambda text: text.encode())

        svc.synthesize("один")
        svc.synthesize("два")
        svc.synthesize("три")  # вытесняет «один»
        assert len(svc._cache) == 2


# ── Модели ─────────────────────────────────────────────────
class TestModels:
    def test_voice_url_dir(self):
        assert _voice_url_dir("ru_RU-irina-medium") == "ru/ru_RU/irina/medium"

    def test_voice_url_dir_invalid(self):
        with pytest.raises(ValueError):
            _voice_url_dir("badname")

    def test_ensure_model_returns_existing(self, tmp_path):
        (tmp_path / "ru_RU-irina-medium.onnx").write_bytes(b"x")
        (tmp_path / "ru_RU-irina-medium.onnx.json").write_text("{}")
        res = ensure_model(tmp_path, "ru_RU-irina-medium")
        assert res is not None
        onnx, cfg = res
        assert onnx.name == "ru_RU-irina-medium.onnx"
        assert cfg.name == "ru_RU-irina-medium.onnx.json"


# ── Эндпоинт ───────────────────────────────────────────────
class _FakeService:
    def __init__(self, audio):
        self._audio = audio

    def synthesize(self, text):
        return self._audio


def _make_client(monkeypatch, audio):
    from backend.tts import router as r
    monkeypatch.setattr(r, "get_tts_service", lambda: _FakeService(audio))
    app = Flask(__name__)
    app.register_blueprint(r.tts_bp)
    app.config["TESTING"] = True
    return app.test_client()


# ── Формирование текста тревоги (только в опасной зоне) ────
# voice_violators: список (имя, [отсутствующие СИЗ]) ТОЛЬКО для реальных
# нарушителей В зоне. Имя и его missing привязаны к одному человеку.
class TestBuildVoiceText:
    def _fn(self):
        # Импортируем из лёгкого модуля, а НЕ из backend.main — иначе тест
        # тянет ultralytics/insightface (тяжёлые) и падает там, где их нет.
        from backend.tts.alert import build_voice_text
        return build_voice_text

    def test_violation_phrase_names_person(self):
        text = self._fn()([("Иван", ["каска"])])
        assert "Иван" in text and "нарушение" in text and "ликвидации" in text

    def test_empty_is_silent(self):
        # Нет нарушителей в зоне (все экипированы или нарушители вне зоны) → пусто.
        assert self._fn()([]) == ""

    def test_no_name_defaults_to_guest(self):
        assert self._fn()([("", ["каска"])]).startswith("Гость")

    def test_names_only_first_violator(self):
        # Иван в каске НЕ попадает в список (он не нарушитель). Озвучиваем Петра —
        # имя берётся от конкретного нарушителя, а не от первого в кадре.
        text = self._fn()([("Пётр", ["жилет"])])
        assert "Пётр" in text and "нарушение" in text

    def test_multiple_violators_mentions_count(self):
        text = self._fn()([("Иван", ["каска"]), ("", ["маска"])])
        assert "Иван" in text and "и ещё 1" in text


class TestBuildApprovedVoiceText:
    def _fn(self):
        from backend.tts.alert import build_approved_voice_text
        return build_approved_voice_text

    def test_empty_is_silent(self):
        assert self._fn()([]) == ""

    def test_single_calm_announcement(self):
        text = self._fn()(["Иван"])
        assert "Иван" in text and "средствах защиты" in text and "Внимание" not in text

    def test_no_name_defaults_to_worker(self):
        assert self._fn()([""]).startswith("Работник")

    def test_multiple_mentions_count(self):
        text = self._fn()(["Иван", "Пётр"])
        assert "Иван" in text and "и ещё 1" in text


class TestVoiceAlertAudioRoute:
    def test_empty_text_400(self, monkeypatch):
        client = _make_client(monkeypatch, b"data")
        assert client.get("/api/voice_alert_audio").status_code == 400
        assert client.get("/api/voice_alert_audio?text=  ").status_code == 400

    def test_unavailable_503(self, monkeypatch):
        client = _make_client(monkeypatch, None)
        resp = client.get("/api/voice_alert_audio?text=Внимание")
        assert resp.status_code == 503

    def test_returns_wav(self, monkeypatch):
        client = _make_client(monkeypatch, b"RIFFfakewav")
        resp = client.get("/api/voice_alert_audio?text=Внимание")
        assert resp.status_code == 200
        assert resp.mimetype == "audio/wav"
        assert resp.data == b"RIFFfakewav"
