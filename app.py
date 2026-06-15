import os
import uuid

import cv2
# Fix for older OpenCV on Jetson (INTER_NEAREST_EXACT missing in apt python3-opencv)
if not hasattr(cv2, 'INTER_NEAREST_EXACT'):
    cv2.INTER_NEAREST_EXACT = cv2.INTER_NEAREST

from ultralytics import YOLO
from flask import Flask, send_file, render_template, Response, request, jsonify, send_from_directory
from main import generate_live_feed, start_live, stop_live, state, annotated_buffers, add_camera, remove_camera, rename_camera, camera_captures, _init_camera_resources
from config import CAMERAS, save_cameras
from waitress import serve

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")

app = Flask(__name__, static_folder=None)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return send_file(index_path)
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    start_live()
    return jsonify({"status": "started"})


@app.route("/stop", methods=["POST"])
def stop():
    stop_live()
    return jsonify({"status": "stopped"})


@app.route("/cameras")
def get_cameras():
    return jsonify({"cameras": {k: v if isinstance(v, int) else v for k, v in CAMERAS.items()}})


@app.route("/api/cameras", methods=["POST"])
def api_add_camera():
    data = request.get_json()
    cam_id = (data.get("name") or "").strip()
    source = data.get("source")
    if not cam_id:
        return jsonify({"error": "Имя камеры не может быть пустым"}), 400
    if not source and source != 0:
        return jsonify({"error": "Источник не может быть пустым"}), 400
    if cam_id in CAMERAS:
        return jsonify({"error": f"Камера '{cam_id}' уже существует"}), 409
    try:
        source_int = int(source)
    except (ValueError, TypeError):
        source_int = source
    add_camera(cam_id, source_int)
    return jsonify({"status": "added", "name": cam_id, "source": source_int}), 201


@app.route("/api/cameras/<cam_id>", methods=["PUT"])
def api_edit_camera(cam_id: str):
    if cam_id not in CAMERAS:
        return jsonify({"error": "Камера не найдена"}), 404
    data = request.get_json()
    source = data.get("source")
    if not source and source != 0:
        return jsonify({"error": "Источник не может быть пустым"}), 400
    try:
        source_int = int(source)
    except (ValueError, TypeError):
        source_int = source
    # При активной детекции — перезапускаем захват
    if state.live_active and cam_id in camera_captures:
        camera_captures[cam_id].stop()
        del camera_captures[cam_id]
    CAMERAS[cam_id] = source_int
    save_cameras()
    if state.live_active:
        _init_camera_resources(cam_id, source_int)
        camera_captures[cam_id].start()
    return jsonify({"status": "updated", "name": cam_id, "source": source_int})


@app.route("/api/cameras/<cam_id>", methods=["DELETE"])
def api_delete_camera(cam_id: str):
    if cam_id not in CAMERAS:
        return jsonify({"error": "Камера не найдена"}), 404
    remove_camera(cam_id)
    return jsonify({"status": "deleted", "name": cam_id})


@app.route("/api/cameras/<cam_id>/rename", methods=["POST"])
def api_rename_camera(cam_id: str):
    data = request.get_json()
    new_name = (data.get("name") or "").strip()
    if not new_name:
        return jsonify({"error": "Имя не может быть пустым"}), 400
    if new_name in CAMERAS:
        return jsonify({"error": f"Камера '{new_name}' уже существует"}), 409
    if not rename_camera(cam_id, new_name):
        return jsonify({"error": "Камера не найдена"}), 404
    return jsonify({"status": "renamed", "old": cam_id, "new": new_name, "source": CAMERAS[new_name]})


@app.route("/video_frame/<cam_id>")
def video_frame(cam_id):
    if cam_id not in CAMERAS:
        return "Камера не найдена", 404
    ann_buf = annotated_buffers.get(cam_id)
    if ann_buf is None:
        return "Буфер не найден", 404
    frame = ann_buf.read()
    if frame is None:
        return b"", 204
    ret, buffer = cv2.imencode('.jpg', frame)
    if not ret:
        return b"", 500
    return Response(buffer.tobytes(), mimetype='image/jpeg')

# Роут для одной камеры
@app.route("/video_feed/<cam_id>")
def video_feed_cam(cam_id: str):
    if cam_id not in CAMERAS:
        return "Камера не найдена", 404
    return Response(
        generate_live_feed(cam_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

# Fallback для совместимости
@app.route("/video_feed")
def video_feed():
    cam_id = list(CAMERAS.keys())[0]
    return Response(
        generate_live_feed(cam_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route("/detection_log")
def detection_log():
    cam_id = request.args.get("cam_id")
    logs   = state.get_log()
    if cam_id:
        logs = [e for e in logs if e.cam_id == cam_id]
    return jsonify({"logs": [
        {"id": e.id, "timestamp": e.timestamp,
         "message": e.message, "category": e.category,
         "cam_id": e.cam_id, "global_id": e.global_id}
        for e in reversed(logs)
    ]})


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/upload", methods=["POST"])
def upload_file():
    from main import model
    file     = request.files["file"]
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    path     = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    if filename.lower().endswith((".png", ".jpg", ".jpeg")):
        img    = cv2.imread(path)
        result = model(img)[0]
        output = os.path.join(UPLOAD_FOLDER, f"result_{filename}")
        cv2.imwrite(output, result.plot())
        return send_file(output, mimetype="image/jpeg")

    elif filename.lower().endswith((".mp4", ".avi", ".mov")):
        cap    = cv2.VideoCapture(path)
        output = os.path.join(UPLOAD_FOLDER, f"result_{filename}")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out    = cv2.VideoWriter(output, fourcc, 20.0,
                                 (int(cap.get(3)), int(cap.get(4))))
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            out.write(model(frame)[0].plot())
        cap.release()
        out.release()
        return send_file(output, mimetype="video/mp4")

    return "Unsupported file type", 400


@app.route("/export_logs")
def export_logs():
    import csv
    from io import StringIO
    csv_data = StringIO()
    csv_data.write('\ufeff')
    writer = csv.writer(csv_data)
    writer.writerow(["Timestamp", "Camera", "Category", "Message"])
    for entry in reversed(state.get_log()):
        writer.writerow([entry.timestamp, entry.cam_id,
                         entry.category.capitalize(), entry.message])
    return Response(
        csv_data.getvalue(),
        mimetype="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=ppe_logs.csv"}
    )


# ── API управления галереей лиц (Re-ID) ──

@app.route("/api/reid/persons")
def reid_list():
    if state.gallery is None:
        return jsonify({"error": "Re-ID не активен"}), 400
    return jsonify({"persons": state.gallery.list_all()})

@app.route("/api/reid/persons/<int:global_id>/rename", methods=["POST"])
def reid_rename(global_id: int):
    if state.gallery is None:
        return jsonify({"error": "Re-ID не активен"}), 400
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Имя не может быть пустым"}), 400
    if state.gallery.rename(global_id, name):
        return jsonify({"status": "renamed", "global_id": global_id, "name": name})
    return jsonify({"error": "Не найдено"}), 404

@app.route("/api/reid/persons/<int:global_id>", methods=["DELETE"])
def reid_delete(global_id: int):
    if state.gallery is None:
        return jsonify({"error": "Re-ID не активен"}), 400
    if state.gallery.delete(global_id):
        return jsonify({"status": "deleted", "global_id": global_id})
    return jsonify({"error": "Не найдено"}), 404

@app.route("/api/reid/clear", methods=["POST"])
def reid_clear():
    if state.gallery is None:
        return jsonify({"error": "Re-ID не активен"}), 400
    state.gallery.clear()
    return jsonify({"status": "cleared"})

@app.route("/api/reid/stats")
def reid_stats():
    if state.gallery is None:
        return jsonify({"error": "Re-ID не активен"}), 400
    return jsonify({
        "total_persons": state.gallery.count,
        "total_approved": len(list(state._approved.keys())) if hasattr(state, '_approved') else 0,
    })


if __name__ == "__main__":
    threads = max(16, len(CAMERAS.keys()) * 3 + 8)
    print("Запуск на http://127.0.0.1:8000")
    serve(app, host='0.0.0.0', port=8000)