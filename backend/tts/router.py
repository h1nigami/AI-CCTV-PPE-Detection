"""HTTP-эндпоинт синтеза речи для голосовых предупреждений.

GET /api/voice_alert_audio?text=...  → audio/wav (200) либо 503, если синтез
недоступен (нет piper/модели) — фронт в этом случае откатывается на Web Speech.
"""
from flask import Blueprint, request, Response, jsonify
from backend.tts.service import get_tts_service

tts_bp = Blueprint("tts", __name__)


@tts_bp.route("/api/voice_alert_audio")
def voice_alert_audio():
    text = (request.args.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty text"}), 400
    audio = get_tts_service().synthesize(text)
    if not audio:
        return jsonify({"error": "tts unavailable"}), 503
    resp = Response(audio, mimetype="audio/wav")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp
