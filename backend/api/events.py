import uuid
import time as time_module
from flask import Blueprint, jsonify, request, Response

from backend.db.engine import get_session
from backend.db.models import Event, EventLabel
from backend.storage.minio_client import get_storage

events_bp = Blueprint("events", __name__)


def _event_to_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "cameraName": e.camera_id,
        "timestamp": e.timestamp,
        "label": e.label.value if e.label else None,
        "subLabel": e.sub_label.value if e.sub_label else None,
        "personName": e.person_name,
        "personId": e.person_id,
        "hasClip": e.has_clip,
        "hasSnapshot": e.has_snapshot,
        "clipUrl": f"/api/events/{e.id}/clip" if e.has_clip else None,
        "snapshotUrl": f"/api/events/{e.id}/snapshot" if e.has_snapshot else None,
        "score": e.score,
        "ppeHelmet": e.ppe_helmet,
        "ppeMask": e.ppe_mask,
        "ppeVest": e.ppe_vest,
        "startTime": e.start_time,
        "endTime": e.end_time,
        "boxX": e.box_x,
        "boxY": e.box_y,
        "boxW": e.box_w,
        "boxH": e.box_h,
    }


@events_bp.route("/api/events", methods=["GET"])
def list_events():
    camera = request.args.get("camera")
    label = request.args.get("label")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    session = get_session()
    query = session.query(Event).order_by(Event.timestamp.desc())
    if camera:
        query = query.filter(Event.camera_id == camera)
    if label:
        query = query.filter(Event.label == label)
    total = query.count()
    events = query.offset(offset).limit(limit).all()
    session.close()

    return jsonify({
        "events": [_event_to_dict(e) for e in events],
        "total": total,
        "offset": offset,
        "limit": limit,
    })


@events_bp.route("/api/events/<event_id>", methods=["GET"])
def get_event(event_id: str):
    session = get_session()
    e = session.query(Event).filter(Event.id == event_id).first()
    session.close()
    if e is None:
        return jsonify({"error": "Event not found"}), 404
    return jsonify({"event": _event_to_dict(e)})


@events_bp.route("/api/events/<event_id>/clip", methods=["GET"])
def get_event_clip(event_id: str):
    session = get_session()
    e = session.query(Event).filter(Event.id == event_id).first()
    session.close()
    if e is None or not e.has_clip:
        return jsonify({"error": "Clip not found"}), 404

    storage = get_storage()
    data = storage.get_clip_data(event_id, e.camera_id)
    if data is None:
        return jsonify({"error": "Clip data not available"}), 404
    return Response(data, mimetype="video/mp4")


@events_bp.route("/api/events/<event_id>/snapshot", methods=["GET"])
def get_event_snapshot(event_id: str):
    session = get_session()
    e = session.query(Event).filter(Event.id == event_id).first()
    session.close()
    if e is None or not e.has_snapshot:
        return jsonify({"error": "Snapshot not found"}), 404

    storage = get_storage()
    data = storage.get_snapshot_data(event_id, e.camera_id)
    if data is None:
        return jsonify({"error": "Snapshot not available"}), 404
    return Response(data, mimetype="image/jpeg")


def create_event_record(
    cam_id: str,
    label: EventLabel,
    person_name: str = None,
    person_id: int = None,
    ppe_helmet: bool = False,
    ppe_mask: bool = False,
    ppe_vest: bool = False,
    box_x: int = None,
    box_y: int = None,
    box_w: int = None,
    box_h: int = None,
    start_time: float = None,
    end_time: float = None,
    has_clip: bool = False,
    has_snapshot: bool = False,
    score: float = None,
) -> str:
    event_id = str(uuid.uuid4())
    now = time_module.time()
    session = get_session()
    try:
        event = Event(
            id=event_id,
            camera_id=cam_id,
            label=label,
            timestamp=now,
            start_time=start_time or now,
            end_time=end_time,
            has_clip=has_clip,
            has_snapshot=has_snapshot,
            person_name=person_name,
            person_id=person_id,
            ppe_helmet=ppe_helmet,
            ppe_mask=ppe_mask,
            ppe_vest=ppe_vest,
            box_x=box_x,
            box_y=box_y,
            box_w=box_w,
            box_h=box_h,
            score=score,
        )
        session.add(event)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Events] Ошибка создания события: {e}")
        raise
    finally:
        session.close()
    return event_id


def update_event_clip(event_id: str, end_time: float):
    session = get_session()
    try:
        e = session.query(Event).filter(Event.id == event_id).first()
        if e:
            e.end_time = end_time
            e.has_clip = True
            session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Events] Ошибка обновления клипа: {e}")
    finally:
        session.close()


def update_event_snapshot(event_id: str):
    session = get_session()
    try:
        e = session.query(Event).filter(Event.id == event_id).first()
        if e:
            e.has_snapshot = True
            session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Events] Ошибка обновления снимка: {e}")
    finally:
        session.close()
