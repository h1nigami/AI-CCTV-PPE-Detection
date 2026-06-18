"""API архива NVR: список сегментов, отдача файла, поиск по времени.

Источник — таблица Recording (индекс сегментов, см. backend/recorder.py).
Отдача файла идёт через send_file с поддержкой Range-запросов (перемотка
в <video> работает из коробки)."""
from __future__ import annotations
import os
from flask import Blueprint, jsonify, request, send_file

from backend.db.engine import get_session
from backend.db.models import Recording

recordings_bp = Blueprint("recordings", __name__)


def _rec_to_dict(r: Recording) -> dict:
    return {
        "id": r.id,
        "cameraId": r.camera_id,
        "startTime": r.start_time,
        "endTime": r.end_time,
        "duration": r.duration,
        "sizeBytes": r.size_bytes,
        "hasMotion": r.has_motion,
        "playUrl": f"/api/recordings/{r.id}/play",
    }


@recordings_bp.route("/api/recordings", methods=["GET"])
def list_recordings():
    cam_id = request.args.get("cam_id") or request.args.get("camera")
    t_from = request.args.get("from", type=float)
    t_to = request.args.get("to", type=float)
    limit = min(int(request.args.get("limit", 200)), 1000)
    offset = int(request.args.get("offset", 0))

    session = get_session()
    try:
        q = session.query(Recording).order_by(Recording.start_time.asc())
        if cam_id:
            q = q.filter(Recording.camera_id == cam_id)
        if t_from is not None:
            q = q.filter(Recording.end_time >= t_from)
        if t_to is not None:
            q = q.filter(Recording.start_time <= t_to)
        total = q.count()
        rows = q.offset(offset).limit(limit).all()
        return jsonify({
            "recordings": [_rec_to_dict(r) for r in rows],
            "total": total, "offset": offset, "limit": limit,
        })
    finally:
        session.close()


@recordings_bp.route("/api/recordings/at", methods=["GET"])
def recording_at():
    """Найти сегмент, покрывающий момент времени `ts` (для клика по timeline)."""
    cam_id = request.args.get("cam_id") or request.args.get("camera")
    ts = request.args.get("ts", type=float)
    if not cam_id or ts is None:
        return jsonify({"error": "cam_id и ts обязательны"}), 400
    session = get_session()
    try:
        r = (session.query(Recording)
             .filter(Recording.camera_id == cam_id,
                     Recording.start_time <= ts, Recording.end_time >= ts)
             .order_by(Recording.start_time.desc()).first())
        if r is None:
            return jsonify({"error": "Сегмент не найден"}), 404
        return jsonify({"recording": _rec_to_dict(r)})
    finally:
        session.close()


@recordings_bp.route("/api/recordings/<rec_id>", methods=["GET"])
def get_recording(rec_id: str):
    session = get_session()
    try:
        r = session.query(Recording).filter(Recording.id == rec_id).first()
        if r is None:
            return jsonify({"error": "Не найдено"}), 404
        return jsonify({"recording": _rec_to_dict(r)})
    finally:
        session.close()


@recordings_bp.route("/api/recordings/<rec_id>/play", methods=["GET"])
def play_recording(rec_id: str):
    session = get_session()
    try:
        r = session.query(Recording).filter(Recording.id == rec_id).first()
        path = r.path if r else None
    finally:
        session.close()
    if not path or not os.path.exists(path):
        return jsonify({"error": "Файл сегмента недоступен"}), 404
    # conditional=True → поддержка Range-запросов (перемотка/докачка в браузере).
    return send_file(path, mimetype="video/mp4", conditional=True)
