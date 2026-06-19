"""Бэкенд-синтез речи (Piper TTS) для голосовых предупреждений."""
from backend.tts.service import PiperTTSService, get_tts_service
from backend.tts.text import normalize_for_tts

__all__ = ["PiperTTSService", "get_tts_service", "normalize_for_tts"]
