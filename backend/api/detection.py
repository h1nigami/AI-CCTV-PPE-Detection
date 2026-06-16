import os
import uuid
import cv2
from flask import Flask, send_file, render_template, Response, request, jsonify, send_from_directory


def configure_detection_routes(app, state, annotated_buffers, generate_live_feed,
                                start_live, stop_live, model):

    @app.route("/start", methods=["POST"])
    def start():
        start_live()
        return jsonify({"status": "started"})

    @app.route("/stop", methods=["POST"])
    def stop():
        stop_live()
        return jsonify({"status": "stopped"})

    @app.route("/video_frame/<cam_id>")
    def video_frame(cam_id):
        from backend.config import CAMERAS
        if cam_id not in CAMERAS:
            return "Камера не найдена", 404
        ann_buf = annotated_buffers.get(cam_id)
        if ann_buf is None:
            return "Буфер не найден", 404
        frame = ann_buf.read()
        if frame is None:
            return b"", 204
        # Качество 85 вместо 95 — на 30-40% быстрее кодирование,
        # визуально разница незаметна при 1280x720
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            return b"", 500
        return Response(
            buffer.tobytes(),
            mimetype='image/jpeg',
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.route("/video_feed/<cam_id>")
    def video_feed_cam(cam_id):
        from backend.config import CAMERAS
        if cam_id not in CAMERAS:
            return "Камера не найдена", 404
        return Response(
            generate_live_feed(cam_id),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                     "Pragma": "no-cache", "Expires": "0"},
        )

    @app.route("/video_feed")
    def video_feed():
        from backend.config import CAMERAS
        cam_id = list(CAMERAS.keys())[0] if CAMERAS else "cam1"
        return Response(
            generate_live_feed(cam_id),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                     "Pragma": "no-cache", "Expires": "0"},
        )

    @app.route("/api/detect-modes", methods=["GET"])
    def api_get_detect_modes():
        from backend.config import DETECT_MODES
        return jsonify({"modes": dict(DETECT_MODES)})

    @app.route("/api/detect-modes", methods=["PUT"])
    def api_set_detect_modes():
        from backend.config import DETECT_MODES, save_detect_modes
        data = request.get_json() or {}
        for key in ("people", "ppe", "faces"):
            if key in data:
                DETECT_MODES[key] = bool(data[key])
        save_detect_modes()
        return jsonify({"status": "updated", "modes": dict(DETECT_MODES)})

    @app.route("/api/status")
    def api_status():
        return jsonify({"running": state.live_active})

    @app.route("/detection_log")
    def detection_log():
        cam_id = request.args.get("cam_id")
        logs = state.get_log()
        if cam_id:
            logs = [e for e in logs if e.cam_id == cam_id]
        return jsonify({"logs": [
            {"id": e.id, "timestamp": e.timestamp,
             "message": e.message, "category": e.category,
             "cam_id": e.cam_id, "global_id": e.global_id}
            for e in reversed(logs)
        ]})

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

    UPLOAD_FOLDER = "uploads"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    @app.route("/upload", methods=["POST"])
    def upload_file():
        file = request.files["file"]
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            img = cv2.imread(path)
            result = model(img)[0]
            output = os.path.join(UPLOAD_FOLDER, f"result_{filename}")
            cv2.imwrite(output, result.plot())
            return send_file(output, mimetype="image/jpeg")
        elif filename.lower().endswith((".mp4", ".avi", ".mov")):
            cap = cv2.VideoCapture(path)
            output = os.path.join(UPLOAD_FOLDER, f"result_{filename}")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output, fourcc, 20.0,
                                  (int(cap.get(3)), int(cap.get(4))))
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(model(frame)[0].plot())
            cap.release()
            out.release()
            return send_file(output, mimetype="video/mp4")
        return "Unsupported file type", 400

    return app
