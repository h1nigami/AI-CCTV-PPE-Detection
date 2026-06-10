import os
import uuid
from asyncio import threads

import cv2
from ultralytics import YOLO
from flask import Flask, send_file, render_template, Response, request, jsonify
from main import generate_live_feed, start_live, stop_live, state
from config import CAMERAS
from waitress import serve

app = Flask(__name__)


@app.route("/")
def index():
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
    return jsonify({"cameras": list(CAMERAS.keys())})


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
         "cam_id": e.cam_id}
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


if __name__ == "__main__":
    threads = max(16, len(CAMERAS.keys()) * 3 + 8)
    print("Запуск на http://127.0.0.1:8000")
    serve(app, host='0.0.0.0', port=8000)